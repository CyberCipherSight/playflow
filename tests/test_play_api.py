import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from playflow.play_api import PlayPublisher


class PublisherTests(unittest.TestCase):
    def setUp(self):
        # Exercise API ordering and payloads without Google credentials or dependencies.
        self.media = ModuleType("googleapiclient.http")
        self.media.MediaFileUpload = Mock(return_value="media")
        self.modules = patch.dict(sys.modules, {"googleapiclient.http": self.media})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.publisher = PlayPublisher.__new__(PlayPublisher)
        self.publisher.service = Mock()
        self.edits = self.publisher.service.edits.return_value
        self.edits.insert.return_value.execute.return_value = {"id": "edit-1"}
        self.edits.bundles.return_value.upload.return_value.execute.return_value = {
            "versionCode": 42
        }
        self.kwargs = dict(
            package_name="com.example.app",
            aab=Path("fixture.aab"),
            track="internal",
            release_status="draft",
            release_notes=[],
            commit=False,
        )

    def test_validation_discards_edit(self):
        result = self.publisher.publish_bundle(**self.kwargs)
        self.edits.validate.assert_called_once()
        self.edits.delete.assert_called_once_with(packageName="com.example.app", editId="edit-1")
        self.edits.commit.assert_not_called()
        self.assertTrue(result["discarded"])

    def test_commit_only_after_validation(self):
        self.kwargs["commit"] = True
        self.publisher.publish_bundle(**self.kwargs)
        names = [call[0] for call in self.edits.mock_calls]
        self.assertLess(names.index("validate().execute"), names.index("commit"))
        self.edits.delete.assert_not_called()

    def test_failed_validation_never_commits_and_cleans_up(self):
        self.kwargs["commit"] = True
        self.edits.validate.return_value.execute.side_effect = RuntimeError("validation failed")
        with self.assertRaisesRegex(RuntimeError, "validation failed"):
            self.publisher.publish_bundle(**self.kwargs)
        self.edits.commit.assert_not_called()
        self.edits.delete.assert_called_once()

    def test_cleanup_does_not_hide_original_failure(self):
        self.edits.tracks.return_value.update.return_value.execute.side_effect = ValueError(
            "track failed"
        )
        self.edits.delete.return_value.execute.side_effect = RuntimeError("cleanup failed")
        with self.assertRaisesRegex(ValueError, "track failed"):
            self.publisher.publish_bundle(**self.kwargs)

    def test_rollout_fraction_sent_to_api(self):
        self.kwargs.update(release_status="inProgress", user_fraction=0.2)
        self.publisher.publish_bundle(**self.kwargs)
        body = self.edits.tracks.return_value.update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["userFraction"], 0.2)
        self.assertEqual(body["releases"][0]["versionCodes"], ["42"])

    def test_invalid_rollout_rejected_before_creating_edit(self):
        self.kwargs["release_status"] = "inProgress"
        with self.assertRaises(ValueError):
            self.publisher.publish_bundle(**self.kwargs)
        self.edits.insert.assert_not_called()

    def _testers(self):
        testers = self.edits.testers.return_value
        testers.get.return_value.execute.return_value = {
            "googleGroups": ["existing@googlegroups.com"]
        }
        testers.update.return_value.execute.return_value = {
            "googleGroups": ["existing@googlegroups.com", "new@googlegroups.com"]
        }
        return testers

    def test_group_configuration_preserves_existing_groups(self):
        testers = self._testers()
        result = self.publisher.configure_testers(
            "com.example.app", "custom-test", ["new@googlegroups.com"]
        )
        self.assertEqual(
            testers.update.call_args.kwargs["body"],
            {"googleGroups": ["existing@googlegroups.com", "new@googlegroups.com"]},
        )
        self.assertTrue(result["discarded"])
        self.edits.bundles.assert_not_called()
        self.edits.commit.assert_not_called()

    def test_group_configuration_verifies_response_before_commit(self):
        testers = self._testers()
        testers.update.return_value.execute.return_value = {"googleGroups": []}
        with self.assertRaisesRegex(RuntimeError, "did not confirm"):
            self.publisher.configure_testers(
                "com.example.app", "custom-test", ["new@googlegroups.com"], commit=True
            )
        self.edits.commit.assert_not_called()
        self.edits.delete.assert_called_once()

    def test_group_configuration_commits_only_after_validation(self):
        self._testers()
        result = self.publisher.configure_testers(
            "com.example.app", "custom-test", ["new@googlegroups.com"], commit=True
        )
        names = [call[0] for call in self.edits.mock_calls]
        self.assertLess(names.index("validate().execute"), names.index("commit"))
        self.assertFalse(result["discarded"])
        self.edits.delete.assert_not_called()

    def test_publish_can_update_testers_in_same_edit(self):
        self._testers()
        self.kwargs["google_groups"] = ["new@googlegroups.com"]
        self.publisher.publish_bundle(**self.kwargs)
        names = [call[0] for call in self.edits.mock_calls]
        self.assertLess(names.index("testers().update"), names.index("validate"))
