from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

APPLICATION_ID_RE = re.compile(r'\bapplicationId\s*(?:=\s*)?["\']([^"\']+)["\']')
IGNORED_DIRS = {".git", ".gradle", ".idea", ".venv", ".playflow", "build", "node_modules"}
ANDROID_NAME = "{http://schemas.android.com/apk/res/android}name"


@dataclass
class Analysis:
    project_dir: str
    manifest_files: list[str]
    gradle_files: list[str]
    package_name: str | None
    permissions: list[str]
    likely_network_use: bool
    likely_location_use: bool
    likely_camera_use: bool
    likely_microphone_use: bool
    likely_contacts_use: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def analyze_project(project_dir: Path, module: str | None = None) -> Analysis:
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Android project directory not found: {project_dir}")
    root = project_dir.joinpath(*module.split(":")) if module else project_dir
    if not root.is_dir():
        raise FileNotFoundError(f"Android module directory not found: {root}")
    manifests: list[Path] = []
    gradle: list[Path] = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        for filename in sorted(files):
            path = Path(directory) / filename
            if filename == "AndroidManifest.xml":
                manifests.append(path)
            elif filename in {"build.gradle", "build.gradle.kts"}:
                gradle.append(path)

    permissions: set[str] = set()
    packages: set[str] = set()
    warnings: list[str] = []
    for path in manifests:
        try:
            document = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Invalid Android manifest: {path}") from exc
        if document.get("package") and path.parent.name == "main":
            packages.add(document.attrib["package"])
        for element in document:
            if element.tag in {"uses-permission", "uses-permission-sdk-23"}:
                if name := element.get(ANDROID_NAME):
                    permissions.add(name)

    # Only the selected module's Gradle file identifies its application.
    module_gradle = [p for p in gradle if p.parent == root] if module else gradle
    ids: set[str] = set()
    dynamic_id = False
    for path in module_gradle:
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|//[^\n]*|/\*[\s\S]*?\*/""",
            lambda match: match[1] or "",
            text,
        )
        matches = APPLICATION_ID_RE.findall(text)
        valid_ids = {x for x in matches if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", x)}
        ids.update(valid_ids)
        if (
            "applicationIdSuffix" in text
            or "productFlavors" in text
            or ("applicationId" in text and not matches)
            or len(valid_ids) != len(set(matches))
        ):
            dynamic_id = True
    candidates = ids or packages
    package = next(iter(candidates)) if len(candidates) == 1 and not dynamic_id else None
    if package is None:
        warnings.append(
            "Package is ambiguous or dynamic; set play.package_name for the built variant."
        )
    warnings.append(
        "Source permissions are conservative hints, not merged-manifest or Data safety proof."
    )
    return Analysis(
        project_dir=str(project_dir),
        manifest_files=[str(p.relative_to(project_dir)) for p in manifests],
        gradle_files=[str(p.relative_to(project_dir)) for p in gradle],
        package_name=package,
        permissions=sorted(permissions),
        likely_network_use="android.permission.INTERNET" in permissions,
        likely_location_use=bool(
            permissions
            & {
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.ACCESS_COARSE_LOCATION",
                "android.permission.ACCESS_BACKGROUND_LOCATION",
            }
        ),
        likely_camera_use="android.permission.CAMERA" in permissions,
        likely_microphone_use="android.permission.RECORD_AUDIO" in permissions,
        likely_contacts_use=any("CONTACTS" in p for p in permissions),
        warnings=warnings,
    )
