"""Check source and wheel contents before publishing a release."""

import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def check(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name)
        if any(part in {".venv", ".playflow", ".git", "__pycache__"} for part in path.parts):
            raise ValueError(f"Private or generated directory in archive: {name}")
        if (
            path.name.startswith((".env", "playflow-session-", "service-account", "credentials"))
            or path.suffix in {".pem", ".key", ".jks", ".keystore", ".p12", ".pfx", ".pyc"}
            or path.name.startswith("upload-password")
        ):
            raise ValueError(f"Private or generated file in archive: {name}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = list((root / "dist").glob("*.tar.gz"))
    wheels = list((root / "dist").glob("*.whl"))
    if not sources or not wheels:
        raise ValueError("Build both a source distribution and wheel first")
    for source in sources:
        with tarfile.open(source) as archive:
            names = archive.getnames()
        check(names)
        for required in (
            "README.md",
            "LICENSE",
            "CONTRIBUTING.md",
            "docs/architecture.md",
            "firefox-recorder/manifest.json",
            "schemas/play-manifest.schema.json",
            "src/playflow/browser_extension/manifest.json",
            "src/playflow/browser_extension/content.js",
            "skills/playflow-publish/SKILL.md",
            "skills/playflow-publish/references/releases.md",
            "skills/playflow-publish/scripts/doctor.py",
            "skills/playflow-publish/references/setup.md",
            "skills/playflow-publish/LICENSE",
            "docs/getting-started.md",
            ".github/workflows/ci.yml",
            ".gitignore",
        ):
            if not any(name.endswith("/" + required) for name in names):
                raise ValueError(f"Missing {required} from {source.name}")
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            config = archive.read("playflow/browser_extension/config.js").decode()
            statements = [
                line.strip()
                for line in config.splitlines()
                if line.strip() and not line.lstrip().startswith("//")
            ]
            if statements != ["globalThis.PlayFlowBridgeConfig = null;"]:
                raise ValueError(
                    "Bridge distribution configuration must not contain session credentials"
                )
        check(names)
        if "playflow/cli.py" not in names:
            raise ValueError(f"Missing CLI from {wheel.name}")
        for asset in ("manifest.json", "background.js", "content.js", "config.js"):
            if f"playflow/browser_extension/{asset}" not in names:
                raise ValueError(f"Missing live bridge asset {asset} from {wheel.name}")
    print("Distribution contents verified")


if __name__ == "__main__":
    main()
