from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .models import AssetConfig
from .requirements import (
    ASSET_SOURCE,
    FEATURE_SIZE,
    ICON_MAX_BYTES,
    ICON_SIZE,
    PHONE_SCREENSHOT_COUNT,
    SCREENSHOT_DIMENSIONS,
    SCREENSHOT_MAX_RATIO,
)


@dataclass
class AssetCheck:
    key: str
    status: str
    message: str
    source: str = ASSET_SOURCE

    def to_dict(self) -> dict:
        return asdict(self)


def _image_check(project: Path, configured: str | None, key: str, kind: str) -> AssetCheck:
    if not configured:
        return AssetCheck(key, "missing", "Configure the asset path relative to project_dir.")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = project / path
    if not path.is_file():
        return AssetCheck(key, "missing", f"Asset file not found: {path}")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                fmt, mode, size = image.format, image.mode, image.size
                has_transparency = "A" in image.getbands() or "transparency" in image.info
                image.verify()
            with Image.open(path) as image:
                image.load()
        with path.open("rb") as stream:
            header = stream.read(26)
        png_depth = header[24] if fmt == "PNG" and len(header) == 26 else None
    except (
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        ValueError,
    ):
        return AssetCheck(key, "error", "File is not a valid supported image.")
    errors = []
    if kind == "icon":
        if fmt != "PNG" or mode != "RGBA" or png_depth != 8:
            errors.append("icon must be 32-bit RGBA PNG")
        if size != ICON_SIZE:
            errors.append("icon must be 512 × 512 pixels")
        if path.stat().st_size > ICON_MAX_BYTES:
            errors.append("icon must be at most 1024 KB")
    else:
        if fmt not in {"PNG", "JPEG"} or mode != "RGB" or has_transparency:
            errors.append("use RGB JPEG or 24-bit PNG without alpha/transparency")
        if fmt == "PNG" and png_depth != 8:
            errors.append("PNG must use 8 bits per RGB channel")
        if kind == "feature" and size != FEATURE_SIZE:
            errors.append("feature graphic must be 1024 × 500 pixels")
        if kind == "screenshot":
            minimum, maximum = SCREENSHOT_DIMENSIONS
            if min(size) < minimum or max(size) > maximum:
                errors.append("screenshot dimensions must be between 320 and 3840 pixels")
            if max(size) > SCREENSHOT_MAX_RATIO * min(size):
                errors.append("longest dimension must be at most twice the shortest")
    if errors:
        return AssetCheck(key, "error", "; ".join(errors))
    return AssetCheck(key, "pass", f"Validated {size[0]} × {size[1]} {fmt} image.")


def validate_assets(project: Path, assets: AssetConfig) -> list[AssetCheck]:
    checks = [
        _image_check(project, assets.icon, "assets.icon", "icon"),
        _image_check(project, assets.feature_graphic, "assets.feature_graphic", "feature"),
    ]
    minimum, maximum = PHONE_SCREENSHOT_COUNT
    count = len(assets.phone_screenshots)
    checks.append(
        AssetCheck(
            "assets.phone_screenshots",
            "pass" if minimum <= count <= maximum else "missing",
            f"Configured {count} phone screenshots; this mobile-only checker requires {minimum}–{maximum}.",
        )
    )
    resolved = [str((project / Path(p).expanduser()).resolve()) for p in assets.phone_screenshots]
    if len(set(resolved)) != len(resolved):
        checks.append(
            AssetCheck(
                "assets.phone_screenshots.duplicates", "error", "Provide distinct screenshot files."
            )
        )
    checks.extend(
        _image_check(project, path, f"assets.phone_screenshots.{index}", "screenshot")
        for index, path in enumerate(assets.phone_screenshots)
    )
    return checks
