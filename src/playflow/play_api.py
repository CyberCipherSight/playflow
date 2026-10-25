from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import Manifest

SCOPE = "https://www.googleapis.com/auth/androidpublisher"


class PlayPublisher:
    def __init__(self, credentials_path: Path):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Publishing needs: pip install 'playflow[publish]'") from exc
        credentials = service_account.Credentials.from_service_account_file(
            str(credentials_path), scopes=[SCOPE]
        )
        self.service = build(
            "androidpublisher", "v3", credentials=credentials, cache_discovery=False
        )

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> "PlayPublisher":
        env_name = manifest.play.service_account_env
        value = os.environ.get(env_name)
        if not value:
            raise RuntimeError(f"Set {env_name} to the service-account JSON path")
        p = Path(value).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        return cls(p)

    @staticmethod
    def _merge_testers(
        edits, package_name: str, edit_id: str, track: str, groups: list[str]
    ) -> dict:
        testers = edits.testers()
        existing = testers.get(packageName=package_name, editId=edit_id, track=track).execute()
        merged = list(
            dict.fromkeys(value.lower() for value in [*existing.get("googleGroups", []), *groups])
        )
        updated = testers.update(
            packageName=package_name,
            editId=edit_id,
            track=track,
            body={"googleGroups": merged},
        ).execute()
        actual = {value.lower() for value in updated.get("googleGroups", [])}
        if not set(merged).issubset(actual):
            raise RuntimeError("Tester update response did not confirm the requested Google Groups")
        return updated

    @staticmethod
    def _finish_edit(edits, package_name: str, edit_id: str, commit: bool) -> dict:
        validated = edits.validate(packageName=package_name, editId=edit_id).execute()
        committed = None
        if commit:
            committed = edits.commit(packageName=package_name, editId=edit_id).execute()
        else:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        return {"validated": validated, "committed": committed, "discarded": not commit}

    @staticmethod
    def _discard_on_error(edits, package_name: str, edit_id: str) -> None:
        try:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        except Exception:
            pass

    def configure_testers(
        self,
        package_name: str,
        track: str,
        google_groups: list[str],
        *,
        commit: bool = False,
    ) -> dict[str, Any]:
        if not google_groups:
            raise ValueError("At least one Google Group is required")
        edits = self.service.edits()
        edit_id = edits.insert(packageName=package_name, body={}).execute()["id"]
        try:
            testers = self._merge_testers(edits, package_name, edit_id, track, google_groups)
            return {
                "edit_id": edit_id,
                "testers": testers,
                **self._finish_edit(edits, package_name, edit_id, commit),
            }
        except Exception:
            self._discard_on_error(edits, package_name, edit_id)
            raise

    def publish_bundle(
        self,
        package_name: str,
        aab: Path,
        track: str,
        release_status: str,
        release_notes: list[dict[str, str]],
        commit: bool,
        user_fraction: float | None = None,
        google_groups: list[str] | None = None,
    ) -> dict[str, Any]:
        from googleapiclient.http import MediaFileUpload

        if release_status in {"inProgress", "halted"}:
            if user_fraction is None or not 0 < user_fraction < 1:
                raise ValueError("Staged releases require 0 < user_fraction < 1")
        elif user_fraction is not None:
            raise ValueError("user_fraction is only valid for staged releases")
        edits = self.service.edits()
        edit = edits.insert(packageName=package_name, body={}).execute()
        edit_id = edit["id"]
        try:
            media = MediaFileUpload(str(aab), mimetype="application/octet-stream", resumable=True)
            bundle = (
                edits.bundles()
                .upload(packageName=package_name, editId=edit_id, media_body=media)
                .execute()
            )
            version_code = str(bundle["versionCode"])
            release: dict[str, Any] = {
                "versionCodes": [version_code],
                "status": release_status,
            }
            if release_notes:
                release["releaseNotes"] = [
                    {"language": x["language"], "text": x["text"]} for x in release_notes
                ]
            if user_fraction is not None:
                release["userFraction"] = user_fraction
            track_body = {"track": track, "releases": [release]}
            track_result = (
                edits.tracks()
                .update(
                    packageName=package_name,
                    editId=edit_id,
                    track=track,
                    body=track_body,
                )
                .execute()
            )
            testers_result = None
            if google_groups:
                testers_result = self._merge_testers(
                    edits, package_name, edit_id, track, google_groups
                )
            return {
                "edit_id": edit_id,
                "bundle": bundle,
                "track": track_result,
                "testers": testers_result,
                **self._finish_edit(edits, package_name, edit_id, commit),
            }
        except Exception:
            self._discard_on_error(edits, package_name, edit_id)
            raise
