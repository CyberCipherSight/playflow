import json
import os
import sqlite3
import subprocess
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from playflow.cli import app
from playflow.firefox import open_console, profiles, resolve_profile
from playflow.models import BrowserConfig

CONSOLE = "https://play.google.com/console/u/2/developers/123/app-list"


class FirefoxTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / "abcd.Profile 4"
        self.profile.mkdir()
        (self.profile / "prefs.js").write_text("// initialized fixture profile\n")
        (self.root / "Profile Groups").mkdir()
        self.database = self.root / "Profile Groups/store.sqlite"
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TABLE Profiles (name TEXT, path TEXT)")
            db.execute("INSERT INTO Profiles VALUES (?, ?)", ("Normal", self.profile.name))
        (self.root / "profiles.ini").write_text(
            "[Profile0]\nName=legacy\nIsRelative=1\nPath=other.profile\n"
        )
        self.roots = patch("playflow.firefox._profile_roots", return_value=[self.root])
        self.roots.start()
        self.addCleanup(self.roots.stop)

    def test_reads_both_profile_formats_without_changing_database(self):
        before = self.database.read_bytes()
        found = profiles()
        self.assertEqual({item["name"] for item in found}, {"Normal", "legacy"})
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(resolve_profile("normal"), self.profile)

    def test_ambiguous_names_require_explicit_path(self):
        other = self.root / "other"
        other.mkdir()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO Profiles VALUES (?, ?)", ("Normal", other.name))
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            resolve_profile("Normal")
        self.assertEqual(resolve_profile("Normal", str(self.profile)), self.profile)

    def test_missing_profile_is_never_created(self):
        missing = self.root / "missing"
        with self.assertRaisesRegex(ValueError, "Not an existing initialized"):
            resolve_profile(None, str(missing))
        self.assertFalse(missing.exists())

    def test_unrecognized_name_never_falls_back_to_another_account(self):
        with self.assertRaisesRegex(ValueError, "Available: Normal, legacy"):
            resolve_profile("unknown")

    def test_launch_uses_selected_existing_profile_without_shell(self):
        with (
            patch.dict(os.environ, {"DISPLAY": ":1"}),
            patch("playflow.firefox.shutil.which", return_value="/usr/bin/firefox"),
            patch("playflow.firefox.subprocess.Popen") as launch,
        ):
            launch.return_value.wait.return_value = 0
            result = open_console(CONSOLE, "normal")
        self.assertEqual(
            launch.call_args.args[0],
            ["/usr/bin/firefox", "--profile", str(self.profile), "--new-tab", CONSOLE],
        )
        self.assertNotIn("shell", launch.call_args.kwargs)
        self.assertEqual(result["status"], "launch_requested")
        self.assertFalse(result["page_verified"])

    def test_failed_launch_does_not_claim_success(self):
        with (
            patch.dict(os.environ, {"DISPLAY": ":1"}),
            patch("playflow.firefox.shutil.which", return_value="firefox"),
            patch("playflow.firefox.subprocess.Popen") as launch,
        ):
            launch.return_value.wait.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "Firefox exited with code 1"):
                open_console(CONSOLE, "Normal")

    def test_running_gui_is_not_killed_when_wait_times_out(self):
        with (
            patch.dict(os.environ, {"DISPLAY": ":1"}),
            patch("playflow.firefox.shutil.which", return_value="firefox"),
            patch("playflow.firefox.subprocess.Popen") as launch,
        ):
            launch.return_value.wait.side_effect = subprocess.TimeoutExpired("firefox", 2)
            result = open_console(CONSOLE, "Normal")
        self.assertEqual(result["status"], "launch_requested")
        launch.return_value.kill.assert_not_called()

    def test_urls_are_checked_before_launch_and_in_manifest(self):
        for url in ("https://evil.example/console/", "file:///tmp/x", CONSOLE + "?token=x"):
            with self.subTest(url=url), patch("playflow.firefox.subprocess.Popen") as launch:
                with self.assertRaises(ValueError):
                    open_console(url, "Normal")
                with self.assertRaises(ValueError):
                    BrowserConfig(console_url=url)
                launch.assert_not_called()

    def test_open_console_cli_does_not_build_or_sign_again(self):
        manifest = self.root / "manifest.yaml"
        manifest.write_text(
            yaml.safe_dump(
                {
                    "app_name": "Fixture",
                    "browser": {
                        "engine": "firefox",
                        "firefox_profile_name": "Normal",
                        "firefox_profile_path": str(self.profile),
                        "console_url": CONSOLE,
                    },
                }
            )
        )
        with (
            patch(
                "playflow.firefox.open_console", return_value={"status": "launch_requested"}
            ) as launch,
            patch("playflow.release.finish_release") as finish,
        ):
            result = CliRunner().invoke(app, ["open-console", "--manifest", str(manifest)])
        self.assertEqual(result.exit_code, 0, result.output)
        launch.assert_called_once_with(CONSOLE, "Normal", str(self.profile))
        finish.assert_not_called()

    def test_release_optional_launch_only_runs_after_success(self):
        with (
            patch("playflow.release.finish_release", return_value={"signature_verified": True}),
            patch("playflow.cli.open_console_cmd") as launch,
        ):
            result = CliRunner().invoke(app, ["finish-release", "--open-console"])
        self.assertEqual(result.exit_code, 0, result.output)
        launch.assert_called_once_with(manifest=Path("play-manifest.yaml"))
        with (
            patch(
                "playflow.release.finish_release", side_effect=RuntimeError("fixture build failure")
            ),
            patch("playflow.cli.open_console_cmd") as launch,
        ):
            result = CliRunner().invoke(app, ["finish-release", "--open-console"])
        self.assertEqual(result.exit_code, 1, result.output)
        launch.assert_not_called()

    def test_profile_listing_cli_is_read_only(self):
        with patch("playflow.firefox.subprocess.Popen") as launch:
            result = CliRunner().invoke(app, ["firefox-profiles"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Normal", {entry["name"] for entry in json.loads(result.output)["profiles"]})
        launch.assert_not_called()
