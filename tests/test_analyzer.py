import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from playflow.analyzer import analyze_project


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "app/src/main/AndroidManifest.xml"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text("""<manifest xmlns:a="http://schemas.android.com/apk/res/android" package="com.example.legacy">
        <!-- <uses-permission a:name="android.permission.RECORD_AUDIO"/> -->
        <uses-permission a:name="android.permission.INTERNET"/>
        <uses-permission-sdk-23 a:name="android.permission.CAMERA"/></manifest>""")

    def test_xml_namespaces_and_comments(self):
        result = analyze_project(self.root, "app")
        self.assertEqual(result.package_name, "com.example.legacy")
        self.assertTrue(result.likely_network_use)
        self.assertTrue(result.likely_camera_use)
        self.assertFalse(result.likely_microphone_use)

    def test_application_id_overrides_legacy_package(self):
        (self.root / "app/build.gradle.kts").write_text('applicationId = "com.example.actual"')
        self.assertEqual(analyze_project(self.root, "app").package_name, "com.example.actual")

    def test_generated_outputs_and_other_modules_ignored(self):
        for name in ("app/build/generated", "library/src/main"):
            path = self.root / name / "AndroidManifest.xml"
            path.parent.mkdir(parents=True)
            path.write_text('<manifest package="com.wrong.library"/>')
        self.assertEqual(len(analyze_project(self.root, "app").manifest_files), 1)

    def test_dynamic_variant_requires_explicit_package(self):
        (self.root / "app/build.gradle").write_text(
            'applicationId "com.example.app"\napplicationIdSuffix ".beta"'
        )
        self.assertIsNone(analyze_project(self.root, "app").package_name)

    def test_namespace_is_not_application_id(self):
        self.manifest.write_text("<manifest/>")
        (self.root / "app/build.gradle").write_text('namespace "com.example.library"')
        self.assertIsNone(analyze_project(self.root, "app").package_name)

    def test_invalid_xml_fails_instead_of_hiding_permissions(self):
        self.manifest.write_text("<manifest")
        with self.assertRaises(ValueError):
            analyze_project(self.root, "app")

    def test_missing_module_fails(self):
        with self.assertRaises(FileNotFoundError):
            analyze_project(self.root, "missing")

    def test_comments_do_not_hide_real_id_or_invent_a_variant(self):
        (self.root / "app/build.gradle").write_text(
            '// applicationId "com.wrong.app"\n'
            'applicationId "com.example.real" // applicationIdSuffix ".fake"\n'
            'def url = "https://example.com"\n'
        )
        self.assertEqual(analyze_project(self.root, "app").package_name, "com.example.real")

    def test_interpolated_id_does_not_fall_back_to_manifest_package(self):
        (self.root / "app/build.gradle").write_text('applicationId "${appPackage}"')
        self.assertIsNone(analyze_project(self.root, "app").package_name)
