from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / "skills/playflow-publish/scripts/community.py"
spec = importlib.util.spec_from_file_location("playflow_community_helper", HELPER)
community = importlib.util.module_from_spec(spec)
spec.loader.exec_module(community)


class CommunityPreferenceTests(unittest.TestCase):
    def test_first_status_does_not_create_state_or_authorize_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing/prefs.json"
            result = community.status(community.read_mode(path))
            self.assertTrue(result["offer_onboarding"])
            self.assertFalse(result["prepare_proposals"])
            self.assertFalse(result["github_write_authorized"])
            self.assertFalse(path.parent.exists())

    def test_opt_in_allows_local_proposals_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prefs.json"
            community.save_mode(path, "review")
            result = community.status(community.read_mode(path))
            self.assertTrue(result["prepare_proposals"])
            self.assertFalse(result["offer_onboarding"])
            self.assertFalse(result["github_write_authorized"])
            self.assertTrue(result["approval_required_for_each_proposal"])
            self.assertEqual(json.loads(path.read_text()), {"schema_version": 1, "mode": "review"})
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_decline_is_remembered_and_can_be_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prefs.json"
            community.save_mode(path, "off")
            result = community.status(community.read_mode(path))
            self.assertFalse(result["offer_onboarding"])
            self.assertFalse(result["prepare_proposals"])
            community.save_mode(path, "ask")
            self.assertEqual(community.read_mode(path), "ask")
            self.assertEqual([p.name for p in path.parent.iterdir()], ["prefs.json"])

    def test_malformed_state_is_not_consent_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prefs.json"
            for content in (
                "{",
                "[]",
                '{"schema_version":2,"mode":"review"}',
                '{"schema_version":1,"mode":"automatic"}',
            ):
                with self.subTest(content=content):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        community.read_mode(path)
                    with self.assertRaises(ValueError):
                        community.save_mode(path, "review")
                    self.assertEqual(path.read_text(), content)

    def test_linked_preference_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            actual = root / "actual.json"
            actual.write_text('{"schema_version":1,"mode":"review"}')
            link = root / "link.json"
            try:
                link.symlink_to(actual)
            except OSError:
                self.skipTest("Symbolic link creation unavailable")
            with self.assertRaises(ValueError):
                community.read_mode(link)
            with self.assertRaises(ValueError):
                community.save_mode(link, "off")
            self.assertEqual(json.loads(actual.read_text())["mode"], "review")

    def test_platform_locations_and_relative_xdg_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(
                community.config_path({"XDG_CONFIG_HOME": str(root)}, "Linux"),
                root / "playflow/community.json",
            )
            self.assertEqual(
                community.config_path({"LOCALAPPDATA": str(root)}, "Windows"),
                root / "playflow/community.json",
            )
            with patch.object(community.Path, "home", return_value=root):
                self.assertEqual(
                    community.config_path({"XDG_CONFIG_HOME": "relative"}, "Linux"),
                    root / ".config/playflow/community.json",
                )

    def test_cli_never_connects_and_errors_do_not_echo_private_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prefs.json"
            output = io.StringIO()
            with patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
                with contextlib.redirect_stdout(output):
                    result = community.main(["--config", str(path), "set", "review"])
                self.assertEqual(result, 0)
                self.assertFalse(json.loads(output.getvalue())["github_write_authorized"])
            path.write_text("private fixture content")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = community.main(["--config", str(path), "status"])
            self.assertEqual(result, 2)
            self.assertNotIn("private fixture content", output.getvalue())
            self.assertNotIn(str(path), output.getvalue())


if __name__ == "__main__":
    unittest.main()
