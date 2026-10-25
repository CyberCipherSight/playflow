"""Export a new GitHub-ready folder from a reviewed source archive, never local state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from check_dist import check
from install_skill import SKILL_FILES

FILES = {
    ".gitignore",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "Makefile",
    "MANIFEST.in",
    "pyproject.toml",
}
DIRECTORIES = {
    ".github",
    "docs",
    "examples",
    "schemas",
    "src",
    "tests",
    "tools",
    "scripts",
    "skills",
    "firefox-recorder",
}
PRIVATE_CONTENT = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})"),
    re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    re.compile(rb'"type"\s*:\s*"service_account"'),
    re.compile(rb"/mnt/disk[0-9]+/|/home/[A-Za-z0-9_.-]+/|[A-Z]:\\Users\\[^\\\s]+\\"),
    re.compile(
        rb"https://play\.google\.com/console/u/\d+/developers/(?!1234567890123456789/|123/|1/)[0-9]{10,}/app/[0-9]{10,}"
    ),
)


def read_public_archive(source: Path) -> dict[str, bytes]:
    selected = {}
    with tarfile.open(source) as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(member.name).parts[0] for member in members if member.name}
        if len(roots) != 1:
            raise ValueError("Expected one source archive root")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError("Unsafe archive path")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Source archive must contain regular files only")
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts:
                raise ValueError("Unexpected source root file")
            # Build-generated metadata is not part of the clean Git repository.
            if relative.name == "PKG-INFO" or any(p.endswith(".egg-info") for p in relative.parts):
                continue
            if str(relative) == "setup.cfg":
                continue
            if str(relative) not in FILES and relative.parts[0] not in DIRECTORIES:
                raise ValueError(f"Unexpected public export file: {relative}")
            check([str(relative)])
            if any(p in {"node_modules", ".cache"} for p in relative.parts):
                raise ValueError("Generated dependency data in export")
            if relative.suffix in {".aab", ".apk", ".mp4", ".sqlite", ".db", ".log"}:
                raise ValueError("Runtime artifact in export")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable archive member")
            with stream:
                data = stream.read()
            if any(pattern.search(data) for pattern in PRIVATE_CONTENT):
                # Never print a matched credential or account identifier.
                raise ValueError(f"Potential private content in {relative}; inspect locally")
            if str(relative) in selected:
                raise ValueError("Duplicate archive member")
            selected[str(relative)] = data
    for required in (
        "pyproject.toml",
        "LICENSE",
        "README.md",
        ".gitignore",
        ".github/workflows/ci.yml",
        "src/playflow/cli.py",
        *("skills/playflow-publish/" + n for n in SKILL_FILES),
    ):
        if required not in selected:
            raise ValueError(f"Missing public export resource: {required}")
    return selected


def export(source: Path, destination: Path) -> dict:
    files = read_public_archive(source)
    bundle = destination.with_suffix(".zip")
    skill_bundle = destination.parent / (destination.name + "-skill.zip")
    for output in (destination, bundle, skill_bundle):
        if output.exists() or output.is_symlink():
            raise FileExistsError(
                "Choose a new export name; existing outputs are never overwritten"
            )
    destination.mkdir(parents=True)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as output:
        for name, data in sorted(files.items()):
            output.writestr(destination.name + "/" + name, data)
    with zipfile.ZipFile(skill_bundle, "w", zipfile.ZIP_DEFLATED) as output:
        for name in SKILL_FILES:
            output.writestr("playflow-publish/" + name, files["skills/playflow-publish/" + name])
    return {
        "file_count": len(files),
        "source_archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "export_zip_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "skill_zip_sha256": hashlib.sha256(skill_bundle.read_bytes()).hexdigest(),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "scope": "Curated source export and pattern checks; independent secret scan required before publication.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdist", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = export(args.sdist, args.output)
    report_path = args.output.parent / (args.output.name + "-export-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Exported {report['file_count']} files, source ZIP and skill ZIP; no Git history copied."
    )


if __name__ == "__main__":
    main()
