"""Inspect the actual selected bundle using a locally installed, pinned bundletool."""

from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .gradle import find_aab
from .signing import DESCRIPTOR, verify_bundle_certificate, verify_upload_key
from .workflow import Workflow

BUNDLETOOL_SHA256 = "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29"
DEFAULT_BUNDLETOOL = Path.home() / ".cache/playflow/tools/bundletool-all-1.18.3.jar"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _java(*args: str) -> str:
    result = subprocess.run(
        ["java", *args], capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode:
        # Tool output may contain machine paths or private context; do not persist it.
        raise RuntimeError("Bundletool validation or manifest inspection failed")
    return result.stdout


def inspect_bundle(
    manifest: Path,
    bundletool: Path = DEFAULT_BUNDLETOOL,
    *,
    tool_sha256: str = BUNDLETOOL_SHA256,
    after_version_code: int | None = None,
    certificate_sha256: str | None = None,
) -> dict:
    workflow = Workflow.from_file(manifest)
    cfg = workflow.manifest
    if not cfg.play.package_name:
        raise ValueError("Set play.package_name before verifying the selected bundle")
    bundle = find_aab(workflow.project, cfg.build.aab_path, cfg.build.module)
    jar = bundletool.expanduser().resolve()
    if not jar.is_file():
        raise FileNotFoundError(
            "Install the official bundletool 1.18.3 jar at the default path or provide --bundletool"
        )
    if digest(jar) != tool_sha256:
        raise ValueError("Bundletool checksum differs from the reviewed SHA-256")
    before = digest(bundle)
    _java("-jar", str(jar), "validate", "--bundle=" + str(bundle))
    with zipfile.ZipFile(bundle) as archive:
        modules = sorted(
            name.split("/")[0]
            for name in archive.namelist()
            if name.count("/") == 2 and name.endswith("/manifest/AndroidManifest.xml")
        )
    if "base" not in modules or len(modules) != len(set(modules)):
        raise ValueError("Expected one base module and unique feature-module manifests")
    observed = {}
    for module in modules:
        xml = ET.fromstring(
            _java(
                "-jar",
                str(jar),
                "dump",
                "manifest",
                "--bundle=" + str(bundle),
                "--module=" + module,
            )
        )
        observed[module] = xml
    base = observed["base"]
    code = int(base.attrib[ANDROID + "versionCode"])
    if base.attrib["package"] != cfg.play.package_name:
        raise ValueError("Built package differs from play.package_name; refusing this artifact")
    if after_version_code is not None and code <= after_version_code:
        raise ValueError("Bundle versionCode must exceed the observed previous Play version code")
    if certificate_sha256 is not None:
        verified_certificate = verify_bundle_certificate(bundle, certificate_sha256)
    else:
        metadata = json.loads((workflow.state.path.parent / "signing" / DESCRIPTOR).read_text())
        verify_upload_key(metadata)
        signed = subprocess.run(
            [
                "jarsigner",
                "-verify",
                "-strict",
                "-keystore",
                metadata["keystore"],
                "-storepass:file",
                metadata["password_file"],
                str(bundle),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if signed.returncode:
            raise RuntimeError(
                "Selected bundle signature is not verified against the saved upload key"
            )
        verified_certificate = metadata["certificate_sha256"]
    if digest(bundle) != before:
        raise RuntimeError("Bundle changed while being verified; inspect the selected file again")
    sdk = base.find("uses-sdk")
    permissions = sorted(
        {
            node.attrib[ANDROID + "name"]
            for xml in observed.values()
            for node in xml
            if node.tag in {"uses-permission", "uses-permission-sdk-23"}
        }
    )
    return {
        "package_name": base.attrib["package"],
        "version_code": code,
        "version_name": base.attrib.get(ANDROID + "versionName"),
        "min_sdk": sdk.attrib.get(ANDROID + "minSdkVersion") if sdk is not None else None,
        "target_sdk": sdk.attrib.get(ANDROID + "targetSdkVersion") if sdk is not None else None,
        "permissions": permissions,
        "components": {
            module: [
                {"type": node.tag, "name": node.attrib.get(ANDROID + "name")}
                for application in xml.findall("application")
                for node in application
                if node.tag in {"activity", "activity-alias", "service", "receiver", "provider"}
            ]
            for module, xml in observed.items()
        },
        "sha256": before,
        "certificate_sha256": verified_certificate,
        "signature_verified": True,
        "bundletool_sha256": tool_sha256,
        "scope": "Artifact identity and signing; Google acceptance and runtime behavior remain separate",
    }
