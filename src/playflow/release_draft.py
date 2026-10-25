"""Reconcile one explicitly selected release draft, without final submission."""

from __future__ import annotations

import re
from pathlib import Path

from .artifacts import DEFAULT_BUNDLETOOL, inspect_bundle
from .bridge import Client, target_prefix
from .console import ConsoleSession
from .workflow import Workflow


def release_plan(
    manifest: Path, release_url: str, artifact: dict, *, track_kind: str = "closed"
) -> dict:
    workflow = Workflow.from_file(manifest)
    cfg = workflow.manifest
    if cfg.browser.engine != "firefox":
        raise ValueError("This draft workflow requires Firefox")
    if track_kind == "closed":
        if not cfg.testing or cfg.testing.mode != "closed":
            raise ValueError("This draft workflow requires explicit closed-testing intent")
    elif track_kind == "production":
        if cfg.play.default_track != "production" or cfg.testing is not None:
            raise ValueError(
                "Production drafts require play.default_track: production and no testing intent"
            )
    else:
        raise ValueError("Supported draft track kinds are closed and production")
    prefix = target_prefix(cfg.browser.console_url)
    if target_prefix(release_url) != prefix or not re.fullmatch(
        re.escape(prefix) + r"tracks/\d+/releases/\d+/prepare", release_url
    ):
        raise ValueError("Use this app's actual release prepare URL, without routing metadata")
    if artifact["package_name"] != cfg.play.package_name:
        raise ValueError("Verified artifact package differs from the configured app")
    if not cfg.release_notes or any(not item.text.strip() for item in cfg.release_notes):
        raise ValueError("Supply nonempty reviewed release notes")
    if len({item.language for item in cfg.release_notes}) != len(cfg.release_notes):
        raise ValueError("Release-note languages must be unique")
    if any(
        not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", x.language)
        for x in cfg.release_notes
    ):
        raise ValueError("Release-note language tags must be plain locale identifiers")
    if any(
        re.search(r"</?[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*>", x.text) for x in cfg.release_notes
    ):
        raise ValueError("Release-note text must not embed locale wrapper tags")
    return {
        "release_url": release_url,
        "track_kind": track_kind,
        "heading": "Create production release"
        if track_kind == "production"
        else "Create closed testing release",
        "artifact": artifact,
        "bundle_control": (
            f"View details for App bundle: {artifact['version_code']} ({artifact['version_name']})"
        ),
        "notes": "\n".join(
            f"<{item.language}>\n{item.text}\n</{item.language}>" for item in cfg.release_notes
        ),
        "final_submission": False,
    }


def apply_draft(
    session: ConsoleSession, plan: dict, upload: dict, *, native_uploaded: bool = False
) -> dict:
    if not native_uploaded and upload.get("sha256") != plan["artifact"]["sha256"]:
        raise ValueError(
            "Bridge captured a different bundle; restart it after selecting this artifact"
        )
    url = plan["release_url"]

    def prepared(page):
        return (
            page.get("url", "").split("?", 1)[0] == url
            and plan["heading"] in page.get("headings", [])
            and not page.get("truncated")
            and any(c.get("name") == "Release notes" for c in page.get("controls", []))
        )

    page = session.inspect()
    if not prepared(page):
        page = session.open(url.removeprefix(session.target), plan["heading"], "Release notes")
    if not prepared(page):
        raise RuntimeError(
            "Expected a complete draft screen for the explicitly selected track kind"
        )

    def bundles(page):
        return [
            c
            for c in page.get("controls", [])
            if c.get("name", "").startswith("View details for App bundle:")
            and c.get("section") == "Upload app bundles"
        ]

    current = bundles(page)
    if not current and any(
        "Uploading " in note
        or "upload is optimised for distribution" in note
        or "upload is optimized for distribution" in note
        for note in page.get("notices", [])
    ):
        # An interrupted caller may have already dispatched the attachment.
        # Observe processing first; never blindly send the same upload again.
        page = session.wait(lambda p: [c["name"] for c in bundles(p)] == [plan["bundle_control"]])
        current = bundles(page)
    if current and [c["name"] for c in current] != [plan["bundle_control"]]:
        raise ValueError("Draft contains another bundle; reconcile it explicitly before uploading")
    if not current:
        if native_uploaded:
            raise ValueError(
                "Expected native upload is not present; this mode never attaches files"
            )
        inputs = [
            c
            for c in page["controls"]
            if c.get("type") == "file" and c.get("accept") == ".aab" and not c.get("disabled")
        ]
        if len(inputs) != 1:
            raise ValueError("Expected exactly one enabled AAB input")
        session.client.request(
            "/command",
            {
                "operation": "attach",
                "target": session.target,
                "control_id": inputs[0]["id"],
                "asset": "bundle",
            },
        )
        page = session.wait(
            lambda page: [c["name"] for c in bundles(page)] == [plan["bundle_control"]]
        )
    notes = session.control(page, "Release notes", "textarea")
    locale_pattern = r"<([A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)>"
    existing_locales = set(re.findall(locale_pattern, notes.get("value", "")))
    requested_locales = set(re.findall(locale_pattern, plan["notes"]))
    if not requested_locales.issubset(existing_locales):
        raise ValueError(
            "Release-note locales do not match this app's supported languages; inspect the "
            "existing wrappers and update the manifest before saving"
        )
    if notes.get("value", "").strip() != plan["notes"].strip():
        session.act("Release notes", "fill", plan["notes"], "textarea")
    page = session.inspect()
    save = (
        session.control(page, "Save as draft", "button")
        if any(c.get("name") == "Save as draft" and not c.get("disabled") for c in page["controls"])
        else None
    )
    if save:
        previous = page["document_id"]
        session.act("Save as draft", tag="button")
        # This Console save replaces its document. Never navigate away while saving.
        session.wait(
            lambda p: (
                bool(p.get("acknowledgements"))
                or "Go to Publishing overview?" in p.get("headings", [])
                or (p.get("document_id") != previous and prepared(p))
            )
        )
        if "Go to Publishing overview?" in session.inspect().get("headings", []):
            session.act("Not now", tag="button")
            session.wait(lambda p: "Go to Publishing overview?" not in p.get("headings", []))
    page = session.open(url.removeprefix(session.target), plan["heading"], "Release notes")
    if not prepared(page) or [c["name"] for c in bundles(page)] != [plan["bundle_control"]]:
        raise RuntimeError("Expected bundle was not retained after reopening the draft")
    if (
        session.control(page, "Release notes", "textarea").get("value", "").strip()
        != plan["notes"].strip()
    ):
        raise RuntimeError("Release notes did not persist after reopening the draft")
    return {
        "status": "draft_verified",
        "release_url": url,
        "artifact": plan["artifact"],
        "attachment_source": "external_native_upload"
        if native_uploaded
        else "manifest_captured_asset",
        "remote_identity_verification": "app_scoped_version_row; remote_hash_not_exposed",
        "verified_document_id": page["document_id"],
        "final_submission": False,
    }


def prepare_draft(
    manifest: Path,
    release_url: str,
    *,
    apply: bool = False,
    bundletool: Path = DEFAULT_BUNDLETOOL,
    after_version_code: int | None = None,
    certificate_sha256: str | None = None,
    track_kind: str = "closed",
    native_uploaded: bool = False,
) -> dict:
    artifact = inspect_bundle(
        manifest,
        bundletool,
        after_version_code=after_version_code,
        certificate_sha256=certificate_sha256,
    )
    plan = release_plan(manifest, release_url, artifact, track_kind=track_kind)
    if not apply:
        return {"status": "preview", "plan": plan, "remote_changes": False}
    workflow = Workflow.from_file(manifest)
    if not workflow.manifest.approvals.allow_browser_write_actions:
        raise ValueError("Enable approvals.allow_browser_write_actions before applying a draft")
    client = Client(manifest)
    upload = client.request("/status").get("uploads", {}).get("bundle", {})
    with workflow.state.stage("console_release_draft") as details:
        result = apply_draft(
            ConsoleSession(client, workflow.manifest.browser.console_url, timeout=120),
            plan,
            upload,
            native_uploaded=native_uploaded,
        )
        details["result"] = result
    return result
