"""Copy the bundled standard Agent Skill to an explicitly selected agent directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SKILL_FILES = (
    "SKILL.md",
    "LICENSE",
    "agents/openai.yaml",
    "scripts/doctor.py",
    "references/setup.md",
    "references/releases.md",
    "references/platforms.md",
)


def install(source: Path, destination: Path) -> None:
    destination = destination.expanduser().absolute()
    if destination.name != "playflow-publish":
        raise ValueError("Destination must be the complete playflow-publish skill folder")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Skill destination already exists; review it before replacing it")
    # Validate the whole source before creating any destination files.
    for name in SKILL_FILES:
        item = source / name
        if not item.is_file() or item.is_symlink():
            raise ValueError(f"Missing or linked skill resource: {name}")
        if any(parent.is_symlink() for parent in item.parents if parent != source.parent):
            raise ValueError("Skill resources must not traverse symbolic links")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    try:
        for name in SKILL_FILES:
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, output)
    except Exception:
        shutil.rmtree(destination)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "skills/playflow-publish"
    install(source, args.destination)
    print(
        "Installed playflow-publish instructions. Install the CLI separately; no browser was opened."
    )


if __name__ == "__main__":
    main()
