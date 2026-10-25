import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from playflow.config import load_manifest, write_example_manifest
from playflow.models import Manifest


class ManifestTests(unittest.TestCase):
    def test_public_contact_and_asset_label_facts_are_explicit(self):
        cfg = Manifest(app_name="Demo", developer_facts={"support_email": "support@example.com"})
        self.assertEqual(cfg.developer_facts.support_email, "support@example.com")
        self.assertIsNone(cfg.assets.ai_generated)
        cfg.assets.ai_generated = []
        self.assertEqual(cfg.assets.ai_generated, [])
        cfg.assets.ai_generated = ["feature_graphic", "feature_graphic"]
        self.assertEqual(cfg.assets.ai_generated, ["feature_graphic"])
        with self.assertRaises(ValidationError):
            Manifest(app_name="Demo", developer_facts={"support_email": "not an address"})
        with self.assertRaises(ValidationError):
            Manifest(app_name="Demo", assets={"ai_generated": ["../secret"]})

    def test_listing_character_limits(self):
        for field, limit in (("title", 30), ("short_description", 80), ("full_description", 4000)):
            with self.subTest(field=field):
                Manifest(app_name="Demo", listing=[{field: "x" * limit}])
                with self.assertRaises(ValidationError):
                    Manifest(app_name="Demo", listing=[{field: "x" * (limit + 1)}])

    def test_release_notes_have_a_per_language_unicode_limit(self):
        Manifest(app_name="Demo", release_notes=[{"text": "🙂" * 500}])
        with self.assertRaises(ValidationError):
            Manifest(app_name="Demo", release_notes=[{"text": "x" * 501}])

    def test_group_addresses_are_normalized_and_deduplicated(self):
        cfg = Manifest(
            app_name="Demo",
            testing={
                "mode": "closed",
                "google_groups": [" Testers@googlegroups.com ", "testers@googlegroups.com"],
            },
        )
        self.assertEqual(cfg.testing.google_groups, ["testers@googlegroups.com"])
        with self.assertRaises(ValidationError):
            Manifest(app_name="Demo", testing={"mode": "closed", "google_groups": ["a group name"]})

    def test_country_scope_cannot_conflict_with_selected_list(self):
        for testing in (
            {"mode": "closed", "country_scope": "all", "countries": ["IN"]},
            {"mode": "closed", "country_scope": "selected"},
            {"mode": "closed", "countries": ["IN"]},
            {"mode": "closed", "country_scope": "selected", "countries": ["India"]},
        ):
            with self.subTest(testing=testing), self.assertRaises(ValidationError):
                Manifest(app_name="Demo", testing=testing)
        cfg = Manifest(
            app_name="Demo",
            testing={"mode": "closed", "country_scope": "selected", "countries": ["in", "IN"]},
        )
        self.assertEqual(cfg.testing.countries, ["IN"])

    def test_unknown_fields_and_versions_rejected(self):
        for data in ({"schema_version": 2}, {"build": {"gradel_task": "oops"}}, {"app_name": " "}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                Manifest.model_validate({"app_name": "Demo", **data})

    def test_module_paths_and_task_scope(self):
        cfg = Manifest(app_name="Demo", build={"module": "mobile:app"})
        self.assertEqual(cfg.build.task, ":mobile:app:bundleRelease")
        cfg.build.gradle_task = ":custom:bundleRelease"
        self.assertEqual(cfg.build.task, ":custom:bundleRelease")
        for module in ("../app", "/tmp", "..", "app/sub"):
            with self.subTest(module=module), self.assertRaises(ValidationError):
                Manifest(app_name="Demo", build={"module": module})

    def test_rollout_configuration(self):
        for play in (
            {"release_status": "inProgress"},
            {"user_fraction": 0.5},
            {"release_status": "halted", "user_fraction": 1},
        ):
            with self.subTest(play=play), self.assertRaises(ValidationError):
                Manifest(app_name="Demo", play=play)
        cfg = Manifest(app_name="Demo", play={"release_status": "inProgress", "user_fraction": 0.1})
        self.assertEqual(cfg.play.user_fraction, 0.1)

    def test_generation_safely_quotes_user_input_and_refuses_overwrite(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            name = 'Demo: "quoted"\nproject_dir: /wrong'
            write_example_manifest(path, name)
            cfg, _ = load_manifest(path)
            self.assertEqual(cfg.app_name, name)
            self.assertEqual(cfg.project_dir, ".")
            with self.assertRaises(FileExistsError):
                write_example_manifest(path, "Other")

    def test_empty_or_non_mapping_yaml_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            for text in ("", "- item", "{invalid"):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    load_manifest(path)

    def test_project_path_is_relative_to_manifest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "android").mkdir()
            cfg = Manifest(app_name="Demo", project_dir="android")
            self.assertEqual(cfg.resolved_project_dir(root / "manifest.yaml"), root / "android")
