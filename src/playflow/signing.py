"""Local upload-key generation and AAB signing, independent of Gradle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
import zipfile
from pathlib import Path

KEYSTORE = "upload-keystore.p12"
DESCRIPTOR = "upload-key.json"
ALIAS = "upload"


def _tool(name: str, arguments: list[str]) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"Install a JDK containing {name}")
    result = subprocess.run(
        [executable, "-J-Duser.language=en", "-J-Duser.country=US", *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        # Do not persist raw tool output or expose secret file contents.
        raise RuntimeError(f"{name} failed (exit {result.returncode})")
    return result.stdout


def _private_new_file(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        if os.name != "nt" and os.fstat(fd).st_mode & 0o077:
            raise PermissionError(
                "This filesystem does not enforce private file permissions. "
                "Choose a password file on a filesystem supporting mode 0600."
            )
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def _fingerprint(pem: str) -> str:
    digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


def create_upload_key(directory: Path, password_file: Path | None = None) -> dict:
    directory = directory.expanduser().resolve()
    password = (password_file or directory / "upload-password.txt").expanduser().resolve()
    keystore = directory / KEYSTORE
    descriptor = directory / DESCRIPTOR
    certificate = directory / "upload-certificate.pem"
    if any(
        path.exists() or path.is_symlink() for path in (keystore, descriptor, certificate, password)
    ):
        raise FileExistsError(
            "Signing files already exist; reuse the existing key instead of replacing it"
        )
    if not shutil.which("keytool"):
        raise RuntimeError("Install a JDK containing keytool")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private_new_file(password, secrets.token_urlsafe(48) + "\n")
    # The lock contains no credentials; it prevents concurrent initialization.
    lock = directory / ".initializing"
    lock_fd = None
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        _tool(
            "keytool",
            [
                "-genkeypair",
                "-noprompt",
                "-storetype",
                "PKCS12",
                "-keystore",
                str(keystore),
                "-storepass:file",
                str(password),
                "-keypass:file",
                str(password),
                "-alias",
                ALIAS,
                "-keyalg",
                "RSA",
                "-keysize",
                "3072",
                "-validity",
                "10950",
                "-dname",
                "CN=PlayFlow Upload Key",
            ],
        )
        keystore.chmod(0o600)
        pem = _tool(
            "keytool",
            [
                "-exportcert",
                "-rfc",
                "-keystore",
                str(keystore),
                "-storepass:file",
                str(password),
                "-alias",
                ALIAS,
            ],
        )
        certificate.write_text(pem, encoding="ascii")
        metadata = {
            "schema_version": 1,
            "alias": ALIAS,
            "store_type": "PKCS12",
            "keystore": str(keystore),
            "password_file": str(password),
            "certificate": str(certificate),
            "certificate_sha256": _fingerprint(pem),
            "algorithm": "RSA",
            "key_size": 3072,
            "validity_days": 10950,
        }
        with descriptor.open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
            stream.write("\n")
        return metadata
    except BaseException:
        # Keep successfully generated keys and their passwords for recovery.
        if not keystore.exists():
            password.unlink(missing_ok=True)
        raise
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            lock.unlink(missing_ok=True)


def _unsigned_aab(path: Path) -> None:
    if path.suffix.lower() != ".aab" or not path.is_file():
        raise ValueError("Provide a release .aab file; an APK cannot be converted by signing it")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Bundle contains duplicate archive entries")
            if not {"BundleConfig.pb", "base/manifest/AndroidManifest.xml"}.issubset(names):
                raise ValueError("File does not have the required Android App Bundle structure")
            if any(
                name.upper().startswith("META-INF/")
                and name.upper().endswith((".SF", ".RSA", ".DSA", ".EC"))
                for name in names
            ):
                raise ValueError(
                    "Bundle is already signed; preserve and verify the existing signing identity"
                )
            if archive.testzip() is not None:
                raise ValueError("Bundle contains a corrupt entry")
    except zipfile.BadZipFile as exc:
        raise ValueError("Bundle is not a valid ZIP archive") from exc


def verify_upload_key(metadata: dict) -> None:
    """Check that the password unlocks the key matching the recorded certificate."""
    if metadata.get("schema_version") != 1:
        raise ValueError("Unsupported upload-key metadata version")
    keystore, password = Path(metadata["keystore"]), Path(metadata["password_file"])
    if not keystore.is_file() or not password.is_file():
        raise FileNotFoundError(
            "Upload key or password file is missing; restore the signing backup"
        )
    pem = _tool(
        "keytool",
        [
            "-exportcert",
            "-rfc",
            "-keystore",
            str(keystore),
            "-storepass:file",
            str(password),
            "-alias",
            metadata["alias"],
        ],
    )
    if _fingerprint(pem) != metadata["certificate_sha256"]:
        raise ValueError("Upload certificate does not match its saved fingerprint")


def verify_bundle_certificate(bundle: Path, expected_sha256: str) -> str:
    """Verify an already-signed bundle using only a pinned public certificate.

    Existing Gradle signing credentials are neither read nor copied. An ephemeral
    truststore contains the matching public certificate, not an upload private key.
    """
    expected = expected_sha256.replace(":", "").upper()
    if not re.fullmatch(r"[A-F0-9]{64}", expected):
        raise ValueError("Supply the full expected upload-certificate SHA-256 fingerprint")
    expected = ":".join(expected[i : i + 2] for i in range(0, 64, 2))
    output = _tool("keytool", ["-printcert", "-rfc", "-jarfile", str(bundle)])
    certificates = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", output, re.S
    )
    matches = [pem for pem in certificates if _fingerprint(pem) == expected]
    if not matches:
        raise ValueError("Bundle does not contain the expected upload certificate")
    with tempfile.TemporaryDirectory(prefix="playflow-public-cert-") as directory:
        root = Path(directory)
        certificate, password = root / "approved.pem", root / "trust-password.txt"
        _private_new_file(certificate, matches[0] + "\n")
        _private_new_file(password, secrets.token_urlsafe(32) + "\n")
        trust = root / "public-trust.p12"
        _tool(
            "keytool",
            [
                "-importcert",
                "-noprompt",
                "-alias",
                "approved-upload",
                "-file",
                str(certificate),
                "-keystore",
                str(trust),
                "-storetype",
                "PKCS12",
                "-storepass:file",
                str(password),
            ],
        )
        _tool(
            "jarsigner",
            [
                "-verify",
                "-strict",
                "-keystore",
                str(trust),
                "-storepass:file",
                str(password),
                str(bundle),
            ],
        )
    return expected


def sign_bundle(aab: Path, directory: Path, output: Path) -> dict:
    """Sign an unsigned AAB copy and verify every entry against the upload key."""
    aab, directory, output = (path.expanduser().resolve() for path in (aab, directory, output))
    _unsigned_aab(aab)
    if output.suffix.lower() != ".aab" or output.exists() or output.is_symlink():
        raise FileExistsError(
            "Choose a new .aab output path; existing bundles are never overwritten"
        )
    metadata = json.loads((directory / DESCRIPTOR).read_text(encoding="utf-8"))
    verify_upload_key(metadata)
    keystore, password = Path(metadata["keystore"]), Path(metadata["password_file"])
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".signing-", dir=output.parent) as temporary:
        signed = Path(temporary) / "signed.aab"
        _tool(
            "jarsigner",
            [
                "-keystore",
                str(keystore),
                "-storetype",
                "PKCS12",
                "-storepass:file",
                str(password),
                "-keypass:file",
                str(password),
                "-digestalg",
                "SHA-256",
                "-sigalg",
                "SHA256withRSA",
                "-signedjar",
                str(signed),
                str(aab),
                metadata["alias"],
            ],
        )
        _tool(
            "jarsigner",
            [
                "-verify",
                "-strict",
                "-keystore",
                str(keystore),
                "-storepass:file",
                str(password),
                str(signed),
                metadata["alias"],
            ],
        )
        # Exclusive publication preserves any file another process created meanwhile.
        with output.open("xb") as stream:
            try:
                with signed.open("rb") as source:
                    shutil.copyfileobj(source, stream)
            except BaseException:
                output.unlink(missing_ok=True)
                raise
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "signed_aab": str(output),
        "signature_verified": True,
        "certificate_sha256": metadata["certificate_sha256"],
        "sha256": digest,
        "scope": "JAR signature verification; package/version and Play acceptance remain separate checks.",
    }
