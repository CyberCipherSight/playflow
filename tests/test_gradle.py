import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from playflow.gradle import find_aab, find_apk


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def artifact(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        return path

    def test_module_scope_excludes_other_apps(self):
        self.artifact("other/build/outputs/bundle/release/other.aab")
        path = self.artifact("app/build/outputs/bundle/release/app.aab")
        self.assertEqual(find_aab(self.root), path)

    def test_multiple_variants_require_explicit_path(self):
        path = self.artifact("app/build/outputs/bundle/release/app.aab")
        self.artifact("app/build/outputs/bundle/debug/app.aab")
        with self.assertRaises(ValueError):
            find_aab(self.root)
        self.assertEqual(find_aab(self.root, str(path)), path)

    def test_configured_artifact_must_be_correct_file_type(self):
        apk = self.artifact("app.apk")
        with self.assertRaises(FileNotFoundError):
            find_aab(self.root, str(apk))
        with self.assertRaises(FileNotFoundError):
            find_aab(self.root, ".")

    def test_nested_module_apk(self):
        path = self.artifact("mobile/app/build/outputs/apk/release/app.apk")
        self.assertEqual(find_apk(self.root, module="mobile:app"), path)
