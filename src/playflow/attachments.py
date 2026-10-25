"""Capture only explicitly configured public release files for a bridge session."""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from pathlib import Path

from PIL import Image

from .models import Manifest

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SESSION_BYTES = 64 * 1024 * 1024


def capture_uploads(cfg: Manifest, project: Path) -> dict[str, dict]:
    selected = {
        "bundle": cfg.build.aab_path,
        "icon": cfg.assets.icon,
        "feature_graphic": cfg.assets.feature_graphic,
        **{f"phone_screenshots.{i}": p for i, p in enumerate(cfg.assets.phone_screenshots)},
    }
    result = {}
    total = 0
    for key, configured in selected.items():
        if not configured:
            continue
        path = Path(configured).expanduser()
        path = (path if path.is_absolute() else project / path).resolve()
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"Configured upload {key} must be a regular file of at most 16 MiB")
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_SESSION_BYTES:
            raise ValueError("Bridge upload capture exceeds its file/session size limit")
        if key == "bundle":
            if path.suffix.lower() != ".aab":
                raise ValueError("Configured bundle must be an AAB")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "base/manifest/AndroidManifest.xml" not in archive.namelist():
                    raise ValueError("Configured bundle lacks its base manifest")
            mime = "application/octet-stream"
        else:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError(f"Configured upload {key} must be PNG or JPEG")
                mime = "image/png" if image.format == "PNG" else "image/jpeg"
                image.verify()
        result[key] = {
            "name": path.name,
            "mime": mime,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "data": base64.b64encode(data).decode("ascii"),
        }
    return result
