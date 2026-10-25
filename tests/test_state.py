import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from playflow.state import StateStore


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StateStore(Path(self.temp.name))

    def test_roundtrip_preserves_other_steps(self):
        self.store.mark("inspect", "done", value=1)
        self.store.mark("build", "done")
        self.assertEqual(self.store.load()["steps"]["inspect"]["value"], 1)

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_state_is_private(self):
        self.store.mark("inspect", "done")
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.path.parent.stat().st_mode & 0o777, 0o700)

    def test_replace_failure_keeps_previous_state(self):
        self.store.mark("inspect", "done")
        before = self.store.path.read_bytes()
        with patch("playflow.state.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.store.mark("build", "done")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.store.path.parent.glob(".state-*")), [])

    def test_failure_record_does_not_save_exception_message(self):
        with self.assertRaises(RuntimeError):
            with self.store.stage("publish"):
                raise RuntimeError("secret-token")
        data = self.store.load()
        self.assertEqual(data["steps"]["publish"]["status"], "failed")
        self.assertNotIn("secret-token", json.dumps(data))

    def test_invalid_state_is_not_silently_overwritten(self):
        self.store.save({"schema_version": 2, "steps": {}})
        with self.assertRaises(ValueError):
            self.store.mark("build", "done")
