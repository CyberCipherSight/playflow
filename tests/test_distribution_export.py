from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from export_prototype import read_public_archive  # noqa: E402
from install_skill import SKILL_FILES, install  # noqa: E402


class ExportSecurityTests(unittest.TestCase):
    def archive(self, root: Path, name: str, data: bytes = b"example", link=False) -> Path:
        path = root / "source.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            if link:
                member.type = tarfile.SYMTYPE
                member.linkname = "/private/file"
                archive.addfile(member)
            else:
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        return path

    def test_rejects_traversal_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, link in (("release/../README.md", False), ("release/README.md", True)):
                with self.subTest(name=name, link=link), self.assertRaises(ValueError):
                    read_public_archive(self.archive(root, name, link=link))

    def test_rejects_private_runtime_and_unselected_root_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in (
                "release/.playflow/facts.json",
                "release/play-manifest.yaml",
                "release/docs/demo.mp4",
            ):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    read_public_archive(self.archive(root, name))

    def test_credentials_fail_without_echoing_value(self):
        secret = b"ghp_" + b"x" * 36
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError) as error:
                read_public_archive(self.archive(Path(folder), "release/README.md", secret))
            self.assertNotIn(secret.decode(), str(error.exception))

    def test_installer_refuses_overwrite_and_copies_only_curated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            for name in SKILL_FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            (source / "private.txt").write_text("not distributable")
            destination = root / "agent/playflow-publish"
            install(source, destination)
            self.assertFalse((destination / "private.txt").exists())
            with self.assertRaises(FileExistsError):
                install(source, destination)
            self.assertEqual((destination / "SKILL.md").read_text(), "SKILL.md")


if __name__ == "__main__":
    unittest.main()
