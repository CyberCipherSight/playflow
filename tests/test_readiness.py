import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from typer.testing import CliRunner

from playflow.analyzer import analyze_project
from playflow.cli import app
from playflow.config import load_manifest
from playflow.models import Manifest
from playflow.readiness import readiness_report, resolve_track


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "app/src/main/AndroidManifest.xml"
        source.parent.mkdir(parents=True)
        source.write_text('<manifest package="com.example.app"/>')
        self.analysis = analyze_project(self.root, "app")

    def test_missing_data_does_not_claim_ready(self):
        cfg = Manifest(app_name="Demo")
        report = readiness_report(cfg, self.root, self.analysis)
        self.assertEqual(report["status"], "blocked")
        keys = {check["key"] for check in report["checks"] if check["status"] == "missing"}
        self.assertIn("assets.icon", keys)
        self.assertIn("build.aab", keys)
        self.assertIn("developer_facts.privacy_policy_url", keys)

    def test_closed_mode_never_silently_uses_internal_or_production(self):
        for track in (None, "internal", "production"):
            cfg = Manifest(
                app_name="Demo", play={"default_track": track}, testing={"mode": "closed"}
            )
            with self.subTest(track=track), self.assertRaises(ValueError):
                resolve_track(cfg)
        cfg.play.default_track = "custom-closed"
        self.assertEqual(resolve_track(cfg), "custom-closed")

    def test_country_request_is_distinct_from_console_completion(self):
        cfg = Manifest(
            app_name="Demo",
            play={"default_track": None},
            testing={
                "mode": "closed",
                "country_scope": "all",
                "google_groups": ["testers@googlegroups.com"],
            },
        )
        report = readiness_report(cfg, self.root, self.analysis)
        self.assertEqual(report["testing_plan"]["country_scope"], "all")
        self.assertEqual(report["testing_plan"]["console_state"], "not_checked")
        self.assertIn(
            "testing.console_configuration",
            {c["key"] for c in report["checks"] if c["status"] == "manual"},
        )

    def test_cli_preflight_is_read_only_and_machine_readable(self):
        path = self.root / "manifest.yaml"
        path.write_text("app_name: Demo\n")
        with patch("playflow.play_api.PlayPublisher.from_manifest") as publisher:
            result = CliRunner().invoke(app, ["preflight", "--manifest", str(path)])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertEqual(json.loads(result.output)["status"], "blocked")
        self.assertFalse((self.root / ".playflow").exists())
        publisher.assert_not_called()

    def test_firefox_config_does_not_launch_chromium(self):
        path = self.root / "manifest.yaml"
        path.write_text(
            "app_name: Demo\nbrowser:\n  engine: firefox\n  firefox_profile_name: normal\n"
        )
        with patch("playflow.browser.authenticate") as authenticate:
            result = CliRunner().invoke(app, ["auth", "--manifest", str(path)])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Use bridge-serve", result.output)
        authenticate.assert_not_called()

    def test_example_closed_testing_manifest_loads(self):
        path = Path(__file__).resolve().parents[1] / "examples/closed-testing.yaml"
        cfg, _ = load_manifest(path)
        self.assertEqual(cfg.testing.mode, "closed")
        self.assertEqual(cfg.testing.country_scope, "all")
        self.assertIsNone(cfg.play.default_track)
