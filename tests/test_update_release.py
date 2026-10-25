import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from playflow.artifacts import digest, inspect_bundle
from playflow.console import ConsoleSession
from playflow.release_draft import apply_draft, prepare_draft, release_plan

APP = "https://play.google.com/console/u/0/developers/123/app/42/"
URL = APP + "tracks/77/releases/2/prepare"
ARTIFACT = {
    "package_name": "com.example.app",
    "version_code": 5,
    "version_name": "0.2.1",
    "sha256": "abc",
}
LABEL = "View details for App bundle: 5 (0.2.1)"


class DraftClient:
    def __init__(
        self,
        *,
        other=False,
        persist=True,
        existing=False,
        empty=False,
        pending=False,
        heading="Create closed testing release",
        pending_notice="Uploading selected.aab",
    ):
        self.notes = (
            "<en-US>\nUpdated controls.\n</en-US>" if existing else "<en-US>\nold\n</en-US>"
        )
        self.saved = self.notes
        self.document = 1
        self.dirty = False
        self.persist = persist
        self.other = other
        self.empty = empty or pending
        self.pending = pending
        self.pending_seen = False
        self.calls = []
        self.heading = heading
        self.pending_notice = pending_notice

    def request(self, endpoint, data):
        self.calls.append(data.copy())
        operation = data["operation"]
        if operation == "attach":
            self.empty = False
        if operation == "inspect" and self.pending_seen:
            self.empty = False
            self.pending = False
        if operation == "inspect" and self.pending:
            self.pending_seen = True
        if operation == "navigate":
            previous = str(self.document)
            self.document += 1
            self.notes = self.saved
            return {"previous_document_id": previous}
        if operation == "fill":
            self.notes = data["value"]
            self.dirty = True
        if operation == "click":
            if self.persist:
                self.saved = self.notes
            self.document += 1
            self.dirty = False
        page = {
            "url": URL,
            "document_id": str(self.document),
            "truncated": False,
            "notices": [self.pending_notice] if self.pending else [],
            "headings": [self.heading],
            "controls": [
                {
                    "id": "bundle",
                    "name": "View details for App bundle: 6 (other)" if self.other else LABEL,
                    "section": "Upload app bundles",
                    "tag": "button",
                },
                {"id": "notes", "name": "Release notes", "tag": "textarea", "value": self.notes},
                {
                    "id": "save",
                    "name": "Save as draft",
                    "tag": "button",
                    "disabled": not self.dirty,
                },
            ],
        }
        if self.empty:
            page["controls"] = [c for c in page["controls"] if c["id"] != "bundle"]
            page["controls"].append({"id": "file", "type": "file", "accept": ".aab"})
        return page


class UpdateReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "play-manifest.yaml"
        self.cfg = {
            "app_name": "Fixture",
            "project_dir": ".",
            "state_dir": ".playflow",
            "build": {"aab_path": "release.aab"},
            "play": {"package_name": "com.example.app"},
            "testing": {"mode": "closed"},
            "browser": {"engine": "firefox", "console_url": APP},
            "approvals": {"allow_browser_write_actions": True},
            "release_notes": [{"language": "en-US", "text": "Updated controls."}],
        }
        self.manifest.write_text(yaml.safe_dump(self.cfg))

    def test_other_app_or_non_prepare_url_refused(self):
        for url in [
            URL.replace("/42/", "/43/"),
            URL + "?source=x",
            URL.replace("prepare", "review"),
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                release_plan(self.manifest, url, ARTIFACT)

    def production_manifest(self):
        self.cfg.pop("testing")
        self.cfg["play"]["default_track"] = "production"
        self.manifest.write_text(yaml.safe_dump(self.cfg))

    def test_production_requires_explicit_manifest_and_track_intent(self):
        with self.assertRaises(ValueError):
            release_plan(self.manifest, URL, ARTIFACT, track_kind="production")
        self.production_manifest()
        with self.assertRaises(ValueError):
            release_plan(self.manifest, URL, ARTIFACT)
        plan = release_plan(self.manifest, URL, ARTIFACT, track_kind="production")
        self.assertEqual(plan["heading"], "Create production release")

    def test_native_production_upload_is_saved_without_attachment_or_key_import(self):
        self.production_manifest()
        client = DraftClient(heading="Create production release")
        plan = release_plan(self.manifest, URL, ARTIFACT, track_kind="production")
        result = apply_draft(ConsoleSession(client, APP), plan, {}, native_uploaded=True)
        self.assertEqual(result["status"], "draft_verified")
        self.assertEqual(result["attachment_source"], "external_native_upload")
        self.assertNotIn("attach", [c["operation"] for c in client.calls])
        self.assertFalse(result["final_submission"])

    def test_native_mode_never_attaches_a_missing_bundle(self):
        client = DraftClient(empty=True)
        with self.assertRaisesRegex(ValueError, "native upload is not present"):
            apply_draft(
                ConsoleSession(client, APP),
                release_plan(self.manifest, URL, ARTIFACT),
                {},
                native_uploaded=True,
            )
        self.assertEqual([c["operation"] for c in client.calls], ["inspect"])

    def test_unsupported_note_locale_is_refused_before_any_write(self):
        client = DraftClient()
        client.notes = client.saved = "<en-GB>\nExisting notes\n</en-GB>"
        with self.assertRaisesRegex(ValueError, "locales do not match"):
            apply_draft(
                ConsoleSession(client, APP),
                release_plan(self.manifest, URL, ARTIFACT),
                {"sha256": "abc"},
            )
        self.assertEqual([c["operation"] for c in client.calls], ["inspect"])

    def test_duplicate_languages_refused(self):
        self.cfg["release_notes"] *= 2
        self.manifest.write_text(yaml.safe_dump(self.cfg))
        with self.assertRaisesRegex(ValueError, "unique"):
            release_plan(self.manifest, URL, ARTIFACT)

    def test_preview_does_not_connect_to_firefox(self):
        with (
            patch("playflow.release_draft.inspect_bundle", return_value=ARTIFACT),
            patch(
                "playflow.release_draft.Client",
                side_effect=AssertionError("Browser must stay closed"),
            ),
        ):
            self.assertFalse(prepare_draft(self.manifest, URL)["remote_changes"])

    def test_stale_session_asset_refused_before_browser_action(self):
        client = DraftClient()
        with self.assertRaisesRegex(ValueError, "different bundle"):
            apply_draft(
                ConsoleSession(client, APP),
                release_plan(self.manifest, URL, ARTIFACT),
                {"sha256": "old"},
            )
        self.assertEqual(client.calls, [])

    def test_another_bundle_refused_without_mutating_it(self):
        client = DraftClient(other=True)
        with self.assertRaisesRegex(ValueError, "another bundle"):
            apply_draft(
                ConsoleSession(client, APP),
                release_plan(self.manifest, URL, ARTIFACT),
                {"sha256": "abc"},
            )
        self.assertEqual([x["operation"] for x in client.calls], ["inspect"])

    def test_existing_bundle_saved_then_verified_in_new_document(self):
        client = DraftClient()
        result = apply_draft(
            ConsoleSession(client, APP),
            release_plan(self.manifest, URL, ARTIFACT),
            {"sha256": "abc"},
        )
        self.assertEqual(result["status"], "draft_verified")
        self.assertFalse(result["final_submission"])
        self.assertEqual([c["operation"] for c in client.calls].count("click"), 1)
        self.assertNotIn("attach", [c["operation"] for c in client.calls])
        self.assertGreater(int(result["verified_document_id"]), 1)

    def test_lost_save_is_not_reported_successful(self):
        with self.assertRaisesRegex(RuntimeError, "notes did not persist"):
            apply_draft(
                ConsoleSession(DraftClient(persist=False), APP),
                release_plan(self.manifest, URL, ARTIFACT),
                {"sha256": "abc"},
            )

    def test_matching_draft_is_verified_without_writes(self):
        client = DraftClient(existing=True)
        apply_draft(
            ConsoleSession(client, APP),
            release_plan(self.manifest, URL, ARTIFACT),
            {"sha256": "abc"},
        )
        self.assertTrue(all(c["operation"] in {"inspect", "navigate"} for c in client.calls))

    def test_empty_draft_attaches_once_then_saves_and_reopens(self):
        client = DraftClient(empty=True)
        result = apply_draft(
            ConsoleSession(client, APP),
            release_plan(self.manifest, URL, ARTIFACT),
            {"sha256": "abc"},
        )
        self.assertEqual(result["status"], "draft_verified")
        self.assertEqual([c["operation"] for c in client.calls].count("attach"), 1)

    def test_in_flight_upload_is_observed_instead_of_reattached(self):
        client = DraftClient(pending=True)
        apply_draft(
            ConsoleSession(client, APP),
            release_plan(self.manifest, URL, ARTIFACT),
            {"sha256": "abc"},
        )
        self.assertNotIn("attach", [c["operation"] for c in client.calls])

    def test_optimizing_upload_is_observed_without_a_second_attachment(self):
        client = DraftClient(
            pending=True,
            pending_notice=(
                "You can leave this page while your selected.aab upload is optimised for distribution."
            ),
        )
        apply_draft(
            ConsoleSession(client, APP),
            release_plan(self.manifest, URL, ARTIFACT),
            {"sha256": "abc"},
        )
        self.assertNotIn("attach", [c["operation"] for c in client.calls])

    def test_embedded_locale_wrappers_are_refused(self):
        self.cfg["release_notes"][0]["text"] = "</en-US><en-US>Unreviewed wrapper"
        self.manifest.write_text(yaml.safe_dump(self.cfg))
        with self.assertRaisesRegex(ValueError, "wrapper"):
            release_plan(self.manifest, URL, ARTIFACT)

    def artifact_files(self):
        jar = self.root / "bundletool.jar"
        jar.write_bytes(b"reviewed jar fixture")
        with zipfile.ZipFile(self.root / "release.aab", "w") as archive:
            for module in ["base", "feature"]:
                archive.writestr(module + "/manifest/AndroidManifest.xml", "protobuf placeholder")
        signing = self.root / ".playflow/signing"
        signing.mkdir(parents=True)
        (signing / "upload-key.json").write_text(
            json.dumps(
                {
                    "keystore": "key",
                    "password_file": "private-password",
                    "certificate_sha256": "fingerprint",
                }
            )
        )
        return jar

    def xml(self, package="com.example.app", permission="android.permission.TRANSMIT_IR"):
        return f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android"
            package="{package}" android:versionCode="5" android:versionName="0.2.1">
            <uses-sdk android:minSdkVersion="23" android:targetSdkVersion="36"/>
            <uses-permission android:name="{permission}"/>
            <application><activity android:name=".MainActivity"/></application></manifest>'''

    def test_inspection_includes_feature_module_permissions(self):
        jar = self.artifact_files()
        with (
            patch(
                "playflow.artifacts._java",
                side_effect=["", self.xml(), self.xml(permission="android.permission.CAMERA")],
            ),
            patch("playflow.artifacts.verify_upload_key"),
            patch("playflow.artifacts.subprocess.run", return_value=SimpleNamespace(returncode=0)),
        ):
            result = inspect_bundle(
                self.manifest, jar, tool_sha256=digest(jar), after_version_code=3
            )
        self.assertEqual(
            result["permissions"], ["android.permission.CAMERA", "android.permission.TRANSMIT_IR"]
        )
        self.assertEqual(result["version_code"], 5)
        self.assertTrue(result["signature_verified"])

    def test_public_certificate_verification_never_reads_a_signing_descriptor(self):
        jar = self.artifact_files()
        (self.root / ".playflow/signing/upload-key.json").unlink()
        with (
            patch("playflow.artifacts._java", side_effect=["", self.xml(), self.xml()]),
            patch(
                "playflow.artifacts.verify_bundle_certificate", return_value="approved-public-cert"
            ) as verify,
            patch(
                "playflow.artifacts.verify_upload_key",
                side_effect=AssertionError("No credential import"),
            ),
        ):
            result = inspect_bundle(
                self.manifest,
                jar,
                tool_sha256=digest(jar),
                certificate_sha256="approved-public-cert",
            )
        self.assertEqual(result["certificate_sha256"], "approved-public-cert")
        verify.assert_called_once()

    def test_package_mismatch_and_reused_version_stop_before_signing(self):
        jar = self.artifact_files()
        for xml, previous in [(self.xml(package="wrong.app"), 3), (self.xml(), 5)]:
            with (
                self.subTest(previous=previous),
                patch("playflow.artifacts._java", side_effect=["", xml, xml]),
                patch(
                    "playflow.artifacts.verify_upload_key",
                    side_effect=AssertionError("Must stop first"),
                ),
                self.assertRaises(ValueError),
            ):
                inspect_bundle(
                    self.manifest, jar, tool_sha256=digest(jar), after_version_code=previous
                )

    def test_unreviewed_bundletool_is_refused(self):
        jar = self.artifact_files()
        with (
            patch("playflow.artifacts._java", side_effect=AssertionError("Must not execute")),
            self.assertRaisesRegex(ValueError, "checksum"),
        ):
            inspect_bundle(self.manifest, jar)


if __name__ == "__main__":
    unittest.main()
