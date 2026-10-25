import base64
import hashlib
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from playflow.attachments import capture_uploads
from playflow.bridge import Session
from playflow.models import Manifest

APP = "https://play.google.com/console/u/0/developers/123/app/42/"


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_only_explicit_files_are_captured_and_bytes_are_stable(self):
        image = self.root / "icon.png"
        Image.new("RGBA", (8, 8)).save(image)
        original = image.read_bytes()
        bundle = self.root / "app.aab"
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr("base/manifest/AndroidManifest.xml", b"fixture")
        (self.root / "credentials.json").write_text('{"private":true}')
        cfg = Manifest(
            app_name="Fixture", assets={"icon": "icon.png"}, build={"aab_path": "app.aab"}
        )
        files = capture_uploads(cfg, self.root)
        image.write_bytes(b"changed after capture")
        self.assertEqual(set(files), {"bundle", "icon"})
        self.assertEqual(base64.b64decode(files["icon"]["data"]), original)
        self.assertEqual(files["icon"]["sha256"], hashlib.sha256(original).hexdigest())
        self.assertNotIn(str(self.root), str(files))

    def test_missing_invalid_and_oversized_files_are_rejected(self):
        path = self.root / "icon.png"
        cfg = Manifest(app_name="Fixture", assets={"icon": "icon.png"})
        with self.assertRaises(ValueError):
            capture_uploads(cfg, self.root)
        path.write_text("not an image")
        with self.assertRaises(OSError):
            capture_uploads(cfg, self.root)
        with path.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "16 MiB"):
            capture_uploads(cfg, self.root)

    def test_non_bundle_zip_is_rejected(self):
        path = self.root / "app.aab"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("credentials.json", b"fixture")
        cfg = Manifest(app_name="Fixture", build={"aab_path": "app.aab"})
        with self.assertRaisesRegex(ValueError, "base manifest"):
            capture_uploads(cfg, self.root)

    def test_attachment_requires_whitelist_scope_and_an_actual_file_control(self):
        uploads = {"icon": {"name": "icon.png", "data": "fixture"}}
        session = Session([APP], True, uploads)
        session.snapshots[APP] = {
            "controls": [{"id": "file:0", "type": "file", "sensitive": True, "name": "Upload"}]
        }
        payload = {"operation": "attach", "target": APP, "control_id": "file:0", "asset": "icon"}
        self.assertEqual(session.validate(payload)["file"], uploads["icon"])
        for asset in ("credentials.json", "../../secret", None):
            with self.subTest(asset=asset), self.assertRaises(ValueError):
                session.validate({**payload, "asset": asset})
        session.snapshots[APP]["controls"][0]["type"] = "password"
        with self.assertRaises(ValueError):
            session.validate(payload)

    def test_attachment_honors_write_gate_and_cannot_target_sites(self):
        site = "https://sites.google.com/d/site-id/"
        for target, write in ((APP, False), (site, True)):
            session = Session([target], write, {"icon": {"name": "icon.png"}})
            session.snapshots[target] = {
                "controls": [{"id": "file:0", "type": "file", "name": "Upload", "sensitive": True}]
            }
            with self.subTest(target=target), self.assertRaises(ValueError):
                session.validate(
                    {
                        "operation": "attach",
                        "target": target,
                        "control_id": "file:0",
                        "asset": "icon",
                    }
                )
