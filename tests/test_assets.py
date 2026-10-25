import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from playflow.assets import validate_assets
from playflow.models import AssetConfig


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = AssetConfig(
            icon="icon.png",
            feature_graphic="feature.png",
            phone_screenshots=["one.png", "two.jpg"],
        )
        self.image("icon.png", (512, 512), "RGBA")
        self.image("feature.png", (1024, 500))
        self.image("one.png", (720, 1280))
        self.image("two.jpg", (720, 1280))

    def image(self, name, size, mode="RGB"):
        Image.new(mode, size).save(self.root / name)

    def check(self, key):
        return next(check for check in validate_assets(self.root, self.config) if check.key == key)

    def test_valid_mobile_assets(self):
        self.assertTrue(
            all(check.status == "pass" for check in validate_assets(self.root, self.config))
        )

    def test_launcher_xml_is_not_a_store_icon(self):
        (self.root / "launcher.xml").write_text("<vector/>")
        self.config.icon = "launcher.xml"
        self.assertEqual(self.check("assets.icon").status, "error")

    def test_icon_requires_dimensions_and_rgba_png(self):
        for size, mode in (((256, 256), "RGBA"), ((512, 512), "RGB")):
            self.image("icon.png", size, mode)
            with self.subTest(size=size, mode=mode):
                self.assertEqual(self.check("assets.icon").status, "error")

    def test_icon_file_size_limit(self):
        Image.new("RGBA", (512, 512)).save(self.root / "icon.png", compress_level=0)
        self.assertGreater((self.root / "icon.png").stat().st_size, 1024 * 1024)
        self.assertEqual(self.check("assets.icon").status, "error")

    def test_feature_graphic_rejects_alpha_and_wrong_dimensions(self):
        for size, mode in (((1024, 500), "RGBA"), ((500, 1024), "RGB")):
            self.image("feature.png", size, mode)
            with self.subTest(size=size, mode=mode):
                self.assertEqual(self.check("assets.feature_graphic").status, "error")

    def test_screenshot_dimension_and_ratio_boundaries(self):
        for size, expected in (
            ((320, 640), "pass"),
            ((320, 641), "error"),
            ((319, 638), "error"),
            ((1921, 3841), "error"),
        ):
            self.image("one.png", size)
            with self.subTest(size=size):
                self.assertEqual(self.check("assets.phone_screenshots.0").status, expected)

    def test_transparent_screenshot_rejected(self):
        self.image("one.png", (720, 1280), "RGBA")
        self.assertEqual(self.check("assets.phone_screenshots.0").status, "error")

    def test_truncated_jpeg_rejected(self):
        path = self.root / "two.jpg"
        path.write_bytes(path.read_bytes()[:-30])
        self.assertEqual(self.check("assets.phone_screenshots.1").status, "error")

    def test_missing_assets_are_actionable(self):
        self.config.icon = "not-found.png"
        self.assertEqual(self.check("assets.icon").status, "missing")

    def test_duplicate_screenshot_paths_rejected(self):
        self.config.phone_screenshots = ["one.png", "./one.png"]
        self.assertEqual(self.check("assets.phone_screenshots.duplicates").status, "error")

    def test_phone_screenshot_count(self):
        for count in (0, 1, 9):
            self.config.phone_screenshots = ["one.png"] * count
            with self.subTest(count=count):
                self.assertEqual(self.check("assets.phone_screenshots").status, "missing")
