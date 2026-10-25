import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from playflow import signing
from playflow.signing import DESCRIPTOR, KEYSTORE, _private_new_file, create_upload_key, sign_bundle


class SigningInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_apk_is_not_accepted_as_bundle(self):
        apk = self.root / "app-debug.apk"
        apk.write_bytes(b"fixture")
        with patch("playflow.signing._tool") as tool:
            with self.assertRaisesRegex(ValueError, "APK cannot be converted"):
                sign_bundle(apk, self.root, self.root / "signed.aab")
        tool.assert_not_called()

    def test_non_bundle_zip_is_rejected(self):
        aab = self.root / "wrong.aab"
        with zipfile.ZipFile(aab, "w") as archive:
            archive.writestr("file.txt", "fixture")
        with self.assertRaisesRegex(ValueError, "required Android App Bundle structure"):
            sign_bundle(aab, self.root, self.root / "signed.aab")

    def test_existing_key_is_never_overwritten(self):
        keystore = self.root / KEYSTORE
        keystore.write_bytes(b"keep-existing-key")
        with self.assertRaises(FileExistsError):
            create_upload_key(self.root)
        self.assertEqual(keystore.read_bytes(), b"keep-existing-key")

    @unittest.skipIf(os.name == "nt", "POSIX permission check")
    def test_password_file_is_removed_if_filesystem_is_not_private(self):
        path = self.root / "secret.txt"
        fake = Mock(st_mode=0o100777)
        with patch("playflow.signing.os.fstat", return_value=fake):
            with self.assertRaises(PermissionError):
                _private_new_file(path, "fixture-secret")
        self.assertFalse(path.exists())

    def test_password_file_never_overwrites_an_existing_file(self):
        path = self.root / "secret.txt"
        path.write_text("keep")
        with self.assertRaises(FileExistsError):
            _private_new_file(path, "replace")
        self.assertEqual(path.read_text(), "keep")


@unittest.skipUnless(
    shutil.which("keytool") and shutil.which("jarsigner"), "JDK signing tools required"
)
class SigningCryptoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.key_dir = cls.root / "key"
        cls.metadata = create_upload_key(cls.key_dir)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def bundle(self, directory):
        path = Path(directory) / "unsigned.aab"
        # A minimal ZIP fixture exercises signatures, not Play/bundletool validity.
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("BundleConfig.pb", b"fixture-config")
            archive.writestr("base/manifest/AndroidManifest.xml", b"fixture-proto-manifest")
            archive.writestr("base/dex/classes.dex", b"fixture-dex")
        return path

    def test_created_password_does_not_appear_in_metadata(self):
        secret = Path(self.metadata["password_file"]).read_text().strip()
        self.assertGreater(len(secret), 40)
        self.assertNotIn(secret, json.dumps(self.metadata))
        self.assertNotIn(secret, (self.key_dir / DESCRIPTOR).read_text())
        if os.name != "nt":
            self.assertEqual(Path(self.metadata["password_file"]).stat().st_mode & 0o777, 0o600)

    def test_actual_signing_verifies_and_preserves_source(self):
        with TemporaryDirectory() as directory:
            aab = self.bundle(directory)
            before = aab.read_bytes()
            output = Path(directory) / "signed.aab"
            result = sign_bundle(aab, self.key_dir, output)
            self.assertTrue(result["signature_verified"])
            self.assertEqual(result["certificate_sha256"], self.metadata["certificate_sha256"])
            self.assertEqual(aab.read_bytes(), before)
            self.assertTrue(output.is_file())
            with self.assertRaises(FileExistsError):
                sign_bundle(aab, self.key_dir, output)
            with self.assertRaisesRegex(ValueError, "already signed"):
                sign_bundle(output, self.key_dir, Path(directory) / "resigned.aab")

    def test_public_certificate_verifies_without_accessing_original_password(self):
        with TemporaryDirectory() as directory:
            aab = self.bundle(directory)
            signed = Path(directory) / "public-verified.aab"
            sign_bundle(aab, self.key_dir, signed)
            password = Path(self.metadata["password_file"])
            saved = password.read_bytes()
            password.unlink()
            try:
                self.assertEqual(
                    signing.verify_bundle_certificate(signed, self.metadata["certificate_sha256"]),
                    self.metadata["certificate_sha256"],
                )
            finally:
                _private_new_file(password, saved.decode())

    def test_public_certificate_rejects_another_key_and_unsigned_added_entries(self):
        with TemporaryDirectory() as directory:
            aab = self.bundle(directory)
            signed = Path(directory) / "modified.aab"
            sign_bundle(aab, self.key_dir, signed)
            with self.assertRaisesRegex(ValueError, "expected upload certificate"):
                signing.verify_bundle_certificate(signed, "00" * 32)
            with zipfile.ZipFile(signed, "a") as archive:
                archive.writestr("untrusted.txt", b"added-after-signing")
            with self.assertRaises(RuntimeError):
                signing.verify_bundle_certificate(signed, self.metadata["certificate_sha256"])

    def test_unsigned_added_entry_fails_strict_verification(self):
        real_tool = signing._tool

        def alter_after_signing(name, arguments):
            result = real_tool(name, arguments)
            if name == "jarsigner" and "-signedjar" in arguments:
                signed = arguments[arguments.index("-signedjar") + 1]
                with zipfile.ZipFile(signed, "a") as archive:
                    archive.writestr("untrusted.txt", b"added-after-signing")
            return result

        with TemporaryDirectory() as directory:
            aab = self.bundle(directory)
            output = Path(directory) / "signed.aab"
            with patch("playflow.signing._tool", side_effect=alter_after_signing):
                with self.assertRaisesRegex(RuntimeError, "jarsigner failed"):
                    sign_bundle(aab, self.key_dir, output)
            self.assertFalse(output.exists())

    def test_password_is_passed_by_file_reference(self):
        real_run = signing.subprocess.run
        secret = Path(self.metadata["password_file"]).read_text().strip()
        with TemporaryDirectory() as directory:
            aab = self.bundle(directory)
            with patch("playflow.signing.subprocess.run", wraps=real_run) as run:
                sign_bundle(aab, self.key_dir, Path(directory) / "signed.aab")
            self.assertNotIn(secret, str(run.call_args_list))
            self.assertTrue(any("-storepass:file" in call.args[0] for call in run.call_args_list))
