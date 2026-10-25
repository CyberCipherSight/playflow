import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import yaml
from typer.testing import CliRunner

from playflow.cli import app
from playflow.workflow import Workflow, run_pipeline


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "play-manifest.yaml"
        self.data = {
            "app_name": "Demo",
            "developer_facts": {
                "contains_ads": False,
                "login_required": False,
                "data_safety_reviewed": True,
            },
        }
        source = self.root / "app/src/main/AndroidManifest.xml"
        source.parent.mkdir(parents=True)
        source.write_text('<manifest package="com.example.app"/>')
        bundle = self.root / "app/build/outputs/bundle/release/app.aab"
        bundle.parent.mkdir(parents=True)
        bundle.write_bytes(b"fixture")
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(yaml.safe_dump(self.data))

    def test_pipeline_blocks_commit_without_approval_before_network(self):
        with (
            patch("playflow.workflow.gradle_build", return_value="secret output"),
            patch("playflow.play_api.PlayPublisher.from_manifest") as publisher,
        ):
            result = run_pipeline(self.manifest, publish=True, commit=True)
        self.assertEqual(result["reason"], "final_approval_required")
        publisher.assert_not_called()
        self.assertNotIn("secret output", Workflow.from_file(self.manifest).state.path.read_text())

    def test_direct_and_pipeline_decline_use_same_gate(self):
        with (
            patch("playflow.workflow.gradle_build", return_value=""),
            patch("playflow.play_api.PlayPublisher.from_manifest") as publisher,
        ):
            workflow = Workflow.from_file(self.manifest)
            first = workflow.publish(workflow.inspect(), commit=True, approve=lambda: False)
            second = run_pipeline(self.manifest, publish=True, commit=True, approve=lambda: False)
        self.assertEqual(first, second)
        publisher.assert_not_called()

    def test_approved_pipeline_commits(self):
        publisher = Mock()
        publisher.publish_bundle.return_value = {"committed": {"id": "test"}}
        with (
            patch("playflow.workflow.gradle_build", return_value=""),
            patch("playflow.play_api.PlayPublisher.from_manifest", return_value=publisher),
        ):
            result = run_pipeline(self.manifest, publish=True, commit=True, approve=lambda: True)
        self.assertEqual(result["status"], "published")
        self.assertTrue(publisher.publish_bundle.call_args.kwargs["commit"])

    def test_policy_blocks_build(self):
        self.data["developer_facts"] = {}
        self.write_manifest()
        with patch("playflow.workflow.gradle_build") as build:
            result = run_pipeline(self.manifest)
        self.assertEqual(result["status"], "blocked")
        build.assert_not_called()

    def test_failed_build_is_not_marked_done(self):
        with patch("playflow.workflow.gradle_build", side_effect=RuntimeError("secret")):
            with self.assertRaises(RuntimeError):
                run_pipeline(self.manifest)
        self.assertEqual(
            Workflow.from_file(self.manifest).state.load()["steps"]["build"]["status"], "failed"
        )

    def test_commit_requires_publish(self):
        with self.assertRaises(ValueError):
            run_pipeline(self.manifest, commit=True)

    def closed_testing(self, track="my-closed-test"):
        self.data["testing"] = {
            "mode": "closed",
            "country_scope": "all",
            "google_groups": ["testers@googlegroups.com"],
        }
        self.data["play"] = {"default_track": track}
        self.write_manifest()

    def test_tester_configuration_requires_commit_approval(self):
        self.closed_testing()
        with patch("playflow.play_api.PlayPublisher.from_manifest") as publisher:
            result = Workflow.from_file(self.manifest).configure_testers(commit=True)
        self.assertEqual(result["reason"], "final_approval_required")
        publisher.assert_not_called()

    def test_tester_configuration_does_not_require_build_or_policy_answers(self):
        self.closed_testing()
        self.data["developer_facts"] = {}
        self.write_manifest()
        publisher = Mock()
        publisher.configure_testers.return_value = {"discarded": True}
        with patch("playflow.play_api.PlayPublisher.from_manifest", return_value=publisher):
            result = Workflow.from_file(self.manifest).configure_testers()
        self.assertEqual(result["status"], "validated")
        publisher.configure_testers.assert_called_once_with(
            "com.example.app", "my-closed-test", ["testers@googlegroups.com"], commit=False
        )

    def test_closed_track_must_be_known_before_any_remote_operation(self):
        self.closed_testing(track=None)
        with patch("playflow.play_api.PlayPublisher.from_manifest") as publisher:
            with self.assertRaises(ValueError):
                Workflow.from_file(self.manifest).configure_testers()
        publisher.assert_not_called()

    def test_custom_state_directory_keeps_external_source_tree_clean(self):
        self.data["state_dir"] = "separate-state"
        self.write_manifest()
        workflow = Workflow.from_file(self.manifest)
        workflow.inspect()
        self.assertEqual(workflow.state.path, self.root / "separate-state/state.json")
        self.assertFalse((self.root / ".playflow").exists())

    def test_publishing_passes_configured_groups_to_adapter(self):
        self.closed_testing()
        publisher = Mock()
        publisher.publish_bundle.return_value = {"discarded": True}
        workflow = Workflow.from_file(self.manifest)
        with patch("playflow.play_api.PlayPublisher.from_manifest", return_value=publisher):
            workflow.publish(workflow.inspect())
        self.assertEqual(
            publisher.publish_bundle.call_args.kwargs["google_groups"], ["testers@googlegroups.com"]
        )
        self.assertEqual(publisher.publish_bundle.call_args.kwargs["track"], "my-closed-test")

    def test_cli_blocked_pipeline_has_nonzero_exit(self):
        self.data["developer_facts"] = {}
        self.write_manifest()
        result = CliRunner().invoke(app, ["run", "--manifest", str(self.manifest)])
        self.assertEqual(result.exit_code, 2, result.output)

    def test_json_output_is_parseable(self):
        import json

        result = CliRunner().invoke(app, ["inspect", "--manifest", str(self.manifest), "--json"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["package_name"], "com.example.app")

    def test_cli_pipeline_asks_for_approval(self):
        with (
            patch("playflow.workflow.gradle_build", return_value=""),
            patch("playflow.play_api.PlayPublisher.from_manifest") as publisher,
        ):
            result = CliRunner().invoke(
                app, ["run", "--manifest", str(self.manifest), "--publish", "--commit"], input="n\n"
            )
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Commit this Play edit?", result.output)
        publisher.assert_not_called()

    def test_cli_missing_manifest_is_a_concise_error(self):
        result = CliRunner().invoke(app, ["inspect", "--manifest", str(self.root / "missing.yaml")])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Manifest not found", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_full_local_pipeline_executes_qualified_gradle_task(self):
        import os

        if os.name == "nt":
            self.skipTest("POSIX fixture wrapper")
        wrapper = self.root / "gradlew"
        wrapper.write_text(
            "#!/bin/sh\n"
            'test "$1" = ":app:bundleRelease" || exit 8\n'
            "mkdir -p app/build/outputs/bundle/release\n"
            "printf fixture > app/build/outputs/bundle/release/app.aab\n"
        )
        result = run_pipeline(self.manifest)
        self.assertEqual(result["status"], "ready")
        state = Workflow.from_file(self.manifest).state.load()
        self.assertEqual(state["steps"]["build"]["status"], "done")
