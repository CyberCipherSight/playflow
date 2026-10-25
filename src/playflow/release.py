"""Local release preparation with durable signing credentials and explicit recovery."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .gradle import find_aab, gradle_wrapper
from .signing import (
    DESCRIPTOR,
    KEYSTORE,
    _private_new_file,
    create_upload_key,
    sign_bundle,
    verify_upload_key,
)
from .workflow import Workflow


def signing_backup_root(identifier: str) -> Path:
    name = re.sub(r"[^a-zA-Z0-9_.-]", "_", identifier).strip(".")[:100] or "app"
    if name != identifier:
        name += "-" + hashlib.sha256(identifier.encode()).hexdigest()[:12]
    return Path.home() / ".config/playflow/signing" / name


def atomic_text(path: Path, content: str) -> None:
    fd, name = tempfile.mkstemp(prefix=".playflow-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.exists():
        if _digest(source) != _digest(destination):
            raise FileExistsError(f"Preserving a different existing file: {destination}")
        return
    with source.open("rb") as original, destination.open("xb") as target:
        shutil.copyfileobj(original, target)
    destination.chmod(0o600)


def _save_descriptor(directory: Path, metadata: dict) -> None:
    atomic_text(directory / DESCRIPTOR, json.dumps(metadata, indent=2) + "\n")


def _backup(metadata: dict, root: Path) -> dict:
    """Verify a complete persistent backup before changing the active descriptor."""
    generation = root / "generations" / uuid.uuid4().hex
    password = generation / "upload-password.txt"
    _private_new_file(password, Path(metadata["password_file"]).read_text(encoding="utf-8"))
    result = dict(metadata)
    for field, filename in (("keystore", KEYSTORE), ("certificate", "upload-certificate.pem")):
        destination = generation / filename
        _copy(Path(metadata[field]), destination)
        result[field] = str(destination)
    result["password_file"] = str(password)
    verify_upload_key(result)
    _save_descriptor(generation, result)
    return result


def prepare_signing(
    directory: Path, backup_root: Path, *, recover_unused_key: bool = False
) -> dict:
    """Restore a matching password or explicitly replace a never-registered key.

    New credentials are created in persistent storage first. Missing credentials
    never trigger automatic rotation. Old signing files and backups are retained.
    """
    directory, backup_root = (p.expanduser().resolve() for p in (directory, backup_root))
    directory.parent.mkdir(parents=True, exist_ok=True)
    lock = directory.parent / ".signing-prepare.lock"
    with lock.open("x"):
        try:
            return _prepare_signing(directory, backup_root, recover_unused_key)
        finally:
            lock.unlink(missing_ok=True)


def _prepare_signing(directory: Path, backup_root: Path, recover_unused_key: bool) -> dict:
    descriptor = directory / DESCRIPTOR
    metadata = json.loads(descriptor.read_text(encoding="utf-8")) if descriptor.is_file() else None
    if metadata is not None:
        fingerprint = metadata["certificate_sha256"].replace(":", "").lower()
        registered = backup_root / "registered" / f"{fingerprint}.json"
        if registered.is_file():
            metadata["registered_with_play"] = True
        # A pre-existing backup may still unlock the original key even if /tmp is gone.
        candidates = [Path(metadata["password_file"]), backup_root / "upload-password.txt"]
        candidates.extend(sorted(backup_root.glob("generations/*/upload-password.txt")))
        for password in dict.fromkeys(candidates):
            if not password.is_file():
                continue
            candidate = {**metadata, "password_file": str(password)}
            try:
                verify_upload_key(candidate)
            except (OSError, RuntimeError, ValueError):
                continue
            # Always copy to a newly created private file; never trust old permissions.
            durable = _backup(candidate, backup_root)
            _save_descriptor(directory, durable)
            return durable
        if metadata.get("registered_with_play"):
            raise RuntimeError(
                "This upload key is recorded as registered with Google Play and cannot be "
                "replaced by --recover-unused-key. Restore its password backup or use "
                "Google Play's upload-key reset process."
            )
        if not recover_unused_key:
            raise RuntimeError(
                "Signing password is missing or cannot unlock the saved key. "
                "Restore its password backup. Only if this key was NEVER uploaded or registered "
                "with Google Play, rerun with --recover-unused-key to archive it and create "
                "a replacement using persistent storage."
            )
    elif directory.exists() and any(directory.iterdir()):
        raise RuntimeError(
            "Signing metadata is missing; preserve these files and restore the backup."
        )

    # Create and verify the replacement before moving any original signing files.
    generation = backup_root / "generations" / uuid.uuid4().hex
    durable = create_upload_key(generation)
    verify_upload_key(durable)
    if metadata is not None:
        archive = directory.parent / "signing-archive" / uuid.uuid4().hex
        archive.parent.mkdir(parents=True, exist_ok=True)
        directory.rename(archive)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    _copy(Path(durable["keystore"]), directory / KEYSTORE)
    _copy(Path(durable["certificate"]), directory / "upload-certificate.pem")
    _save_descriptor(directory, durable)
    return durable


def record_key_registration(
    directory: Path, backup_root: Path, package_name: str, certificate_sha256: str
) -> dict:
    """Record a confirmed Play upload; this function does not query Google or upload anything."""
    metadata = json.loads((directory / DESCRIPTOR).read_text(encoding="utf-8"))
    if metadata["certificate_sha256"] != certificate_sha256:
        raise ValueError("Confirmed upload certificate differs from the active key")
    verify_upload_key(metadata)
    fingerprint = certificate_sha256.replace(":", "").lower()
    registered = backup_root / "registered"
    registered.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = registered / f"{fingerprint}.json"
    record = {
        "schema_version": 1,
        "package_name": package_name,
        "certificate_sha256": certificate_sha256,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source": "confirmed_play_upload",
    }
    if marker.is_file():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if (
            previous.get("package_name") != package_name
            or previous.get("certificate_sha256") != certificate_sha256
        ):
            raise ValueError("Preserving a registration record belonging to another package")
        record = previous
    else:
        atomic_text(marker, json.dumps(record, indent=2) + "\n")
    metadata["registered_with_play"] = True
    _save_descriptor(directory, metadata)
    generation = Path(metadata["password_file"]).parent
    if generation.is_relative_to(backup_root) and (generation / DESCRIPTOR).is_file():
        _save_descriptor(generation, metadata)
    return record


def finish_release(manifest: Path, *, recover_unused_key: bool = False) -> dict:
    """Back up signing material, build, sign and select an AAB without uploading."""
    workflow = Workflow.from_file(manifest)
    cfg = workflow.manifest
    state = workflow.state.path.parent
    signing = state / "signing"
    metadata = prepare_signing(
        signing,
        signing_backup_root(cfg.play.package_name or cfg.app_name),
        recover_unused_key=recover_unused_key,
    )
    workflow.state.mark("signing_key", "done", metadata=metadata)
    print(
        "Signing credentials verified and backed up under ~/.config/playflow/signing/.", flush=True
    )

    # Ignore private material before placing the encrypted key in the source project.
    ignore_path = workflow.project / ".gitignore"
    ignore = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
    rules = ["/.playflow/", "*.jks", "*.keystore", "*.p12", "*.pfx", "upload-password*.txt"]
    missing = [rule for rule in rules if rule not in ignore.splitlines()]
    if missing:
        atomic_text(
            ignore_path,
            ignore.rstrip() + "\n\n# Private local signing material\n" + "\n".join(missing) + "\n",
        )
    # Each certificate gets a distinct folder; a prior local key is never overwritten.
    fingerprint = metadata["certificate_sha256"].replace(":", "").lower()
    project_signing = workflow.project / ".playflow/signing" / fingerprint
    _copy(Path(metadata["keystore"]), project_signing / KEYSTORE)
    _copy(Path(metadata["certificate"]), project_signing / "upload-certificate.pem")
    subprocess.run(
        [str(gradle_wrapper(workflow.project)), cfg.build.task, "--stacktrace"],
        cwd=workflow.project,
        check=True,
    )
    # A previous successful run may have set aab_path to its signed output.
    aab = find_aab(workflow.project, module=cfg.build.module)
    output = (
        state / "artifacts" / f"app-release-signed-{_digest(aab)[:12]}-{uuid.uuid4().hex[:12]}.aab"
    )
    result = sign_bundle(aab, signing, output)
    manifest_path = manifest.expanduser().resolve()
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data.setdefault("build", {})["aab_path"] = os.path.relpath(output, workflow.project)
    atomic_text(manifest_path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    workflow.state.mark("build", "done", aab=str(aab))
    workflow.state.mark("sign_bundle", "done", result=result)
    return result
