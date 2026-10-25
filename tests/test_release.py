import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from playflow.cli import app
from playflow.release import finish_release, prepare_signing, record_key_registration
from playflow.signing import DESCRIPTOR, KEYSTORE, create_upload_key, verify_upload_key


@unittest.skipUnless(
    shutil.which("keytool") and shutil.which("jarsigner"), "JDK signing tools required"
)
class ReleaseRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = TemporaryDirectory()
        cls.fixture_key = Path(cls.fixture.name) / "key"
        create_upload_key(cls.fixture_key)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.signing = self.root / "state/signing"
        shutil.copytree(self.fixture_key, self.signing)
        self.backup = self.root / "persistent-backup"
        self.metadata = json.loads((self.signing / DESCRIPTOR).read_text())
        for field in ("keystore", "certificate", "password_file"):
            self.metadata[field] = str(self.signing / Path(self.metadata[field]).name)
        (self.signing / DESCRIPTOR).write_text(json.dumps(self.metadata))

    def lose_password(self):
        password = Path(self.metadata["password_file"])
        content = password.read_text()
        password.unlink()
        return content

    def test_missing_password_never_rotates_automatically(self):
        self.lose_password()
        before = (self.signing / KEYSTORE).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "NEVER uploaded or registered"):
            prepare_signing(self.signing, self.backup)
        self.assertEqual((self.signing / KEYSTORE).read_bytes(), before)
        self.assertFalse(self.backup.exists())
        self.assertFalse((self.signing.parent / "signing-archive").exists())

    def test_matching_backup_restores_original_identity(self):
        secret = self.lose_password()
        self.backup.mkdir()
        (self.backup / "upload-password.txt").write_text(secret)
        result = prepare_signing(self.signing, self.backup, recover_unused_key=True)
        verify_upload_key(result)
        self.assertEqual(result["certificate_sha256"], self.metadata["certificate_sha256"])
        self.assertTrue(Path(result["password_file"]).is_relative_to(self.backup))
        self.assertNotIn(secret.strip(), json.dumps(result))
        self.assertFalse((self.signing.parent / "signing-archive").exists())
        if os.name != "nt":
            self.assertEqual(Path(result["password_file"]).stat().st_mode & 0o777, 0o600)

    def test_registered_key_cannot_use_unused_key_recovery_even_with_an_old_descriptor(self):
        record_key_registration(
            self.signing, self.backup, "com.example.fixture", self.metadata["certificate_sha256"]
        )
        # Simulate restoring an old descriptor from before the first successful upload.
        (self.signing / DESCRIPTOR).write_text(json.dumps(self.metadata))
        self.lose_password()
        before = (self.signing / KEYSTORE).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "recorded as registered"):
            prepare_signing(self.signing, self.backup, recover_unused_key=True)
        self.assertEqual((self.signing / KEYSTORE).read_bytes(), before)
        self.assertFalse((self.signing.parent / "signing-archive").exists())

    def test_registration_does_not_prevent_restoring_the_same_key(self):
        record_key_registration(
            self.signing, self.backup, "com.example.fixture", self.metadata["certificate_sha256"]
        )
        secret = self.lose_password()
        (self.backup / "upload-password.txt").write_text(secret)
        restored = prepare_signing(self.signing, self.backup, recover_unused_key=True)
        self.assertEqual(restored["certificate_sha256"], self.metadata["certificate_sha256"])
        self.assertTrue(restored["registered_with_play"])

    def test_wrong_registration_fingerprint_is_rejected_before_writes(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            record_key_registration(self.signing, self.backup, "com.example.fixture", "00:11")
        self.assertFalse(self.backup.exists())

    def test_wrong_backup_password_cannot_be_adopted(self):
        self.lose_password()
        self.backup.mkdir()
        backup = self.backup / "upload-password.txt"
        backup.write_text("incorrect-password")
        before = (self.signing / DESCRIPTOR).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Signing password is missing"):
            prepare_signing(self.signing, self.backup)
        self.assertEqual((self.signing / DESCRIPTOR).read_bytes(), before)
        self.assertEqual(backup.read_text(), "incorrect-password")

    def test_explicit_unused_recovery_archives_key_and_uses_durable_password(self):
        self.lose_password()
        old_key = (self.signing / KEYSTORE).read_bytes()
        result = prepare_signing(self.signing, self.backup, recover_unused_key=True)
        verify_upload_key(result)
        self.assertNotEqual(result["certificate_sha256"], self.metadata["certificate_sha256"])
        archive = list((self.signing.parent / "signing-archive").iterdir())
        self.assertEqual(len(archive), 1)
        self.assertEqual((archive[0] / KEYSTORE).read_bytes(), old_key)
        self.assertTrue(Path(result["password_file"]).is_relative_to(self.backup))
        backup_metadata = Path(result["password_file"]).parent / DESCRIPTOR
        self.assertEqual(json.loads(backup_metadata.read_text()), result)
        self.assertEqual(json.loads((self.signing / DESCRIPTOR).read_text()), result)

    def test_failed_replacement_preserves_original_key(self):
        self.lose_password()
        before = (self.signing / KEYSTORE).read_bytes()
        with patch("playflow.release.create_upload_key", side_effect=PermissionError("fixture")):
            with self.assertRaises(PermissionError):
                prepare_signing(self.signing, self.backup, recover_unused_key=True)
        self.assertEqual((self.signing / KEYSTORE).read_bytes(), before)
        self.assertFalse((self.signing.parent / "signing-archive").exists())

    def manifest(self):
        project = self.root / "android"
        project.mkdir()
        manifest = self.root / "manifest.yaml"
        manifest.write_text(
            yaml.safe_dump(
                {
                    "app_name": "Fixture",
                    "project_dir": "android",
                    "state_dir": "state",
                    "play": {"package_name": "com.example.fixture"},
                }
            )
        )
        return project, manifest

    def test_missing_password_cli_explains_recovery_without_building(self):
        self.lose_password()
        _, manifest = self.manifest()
        with (
            patch("playflow.release.signing_backup_root", return_value=self.backup),
            patch("playflow.release.subprocess") as subprocess,
        ):
            result = CliRunner().invoke(app, ["finish-release", "--manifest", str(manifest)])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("--recover-unused-key", result.output)
        self.assertNotIn("Traceback", result.output)
        subprocess.run.assert_not_called()

    def test_finish_release_builds_and_signs_and_can_run_again(self):
        project, manifest = self.manifest()
        (project / "gradlew").write_text("fixture")
        aab = project / "app/build/outputs/bundle/release/app-release.aab"
        aab.parent.mkdir(parents=True)

        def build(*args, **kwargs):
            self.assertIn("/.playflow/", (project / ".gitignore").read_text())
            with zipfile.ZipFile(aab, "w") as archive:
                archive.writestr("BundleConfig.pb", b"fixture-config")
                archive.writestr("base/manifest/AndroidManifest.xml", b"fixture-manifest")

        with (
            patch("playflow.release.signing_backup_root", return_value=self.backup),
            patch("playflow.release.subprocess") as subprocess,
        ):
            subprocess.run.side_effect = build
            first = finish_release(manifest)
            second = finish_release(manifest)
        self.assertTrue(first["signature_verified"])
        self.assertTrue(second["signature_verified"])
        self.assertNotEqual(first["signed_aab"], second["signed_aab"])
        self.assertTrue(Path(first["signed_aab"]).is_file())
        selected = yaml.safe_load(manifest.read_text())["build"]["aab_path"]
        self.assertEqual((project / selected).resolve(), Path(second["signed_aab"]))
