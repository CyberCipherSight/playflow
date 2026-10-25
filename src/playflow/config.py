from __future__ import annotations

from pathlib import Path

import yaml

from .models import Listing, Manifest, ReleaseNotes

DEFAULT_MANIFEST = "play-manifest.yaml"


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> tuple[Manifest, Path]:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Manifest not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {p}") from exc
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML mapping")
    return Manifest.model_validate(data), p


def write_example_manifest(path: Path, app_name: str) -> None:
    manifest = Manifest(
        app_name=app_name,
        listing=[Listing()],
        release_notes=[ReleaseNotes(text="Initial release")],
    )
    # Serialize user input rather than interpolating it into YAML.
    with path.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(manifest.model_dump(), stream, sort_keys=False, allow_unicode=True)
