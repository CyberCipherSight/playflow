from __future__ import annotations

import os
from pathlib import Path

from .shell import run


def gradle_wrapper(project_dir: Path) -> Path:
    wrapper = project_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if not wrapper.is_file():
        raise FileNotFoundError(f"Gradle wrapper not found: {wrapper}")
    if os.name != "nt" and not os.access(wrapper, os.X_OK):
        wrapper.chmod(wrapper.stat().st_mode | 0o100)
    return wrapper


def build(project_dir: Path, task: str) -> str:
    wrapper = gradle_wrapper(project_dir)
    cp = run([str(wrapper), task, "--stacktrace"], cwd=project_dir)
    return cp.stdout


def _artifact(project_dir: Path, configured: str | None, module: str, kind: str) -> Path:
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = project_dir / path
        if not path.is_file() or path.suffix != f".{kind}":
            raise FileNotFoundError(f"Configured {kind.upper()} is not a .{kind} file: {path}")
        return path.resolve()
    output = "bundle" if kind == "aab" else "apk"
    root = project_dir.joinpath(*module.split(":"), "build", "outputs", output)
    candidates = sorted(p.resolve() for p in root.rglob(f"*.{kind}") if p.is_file())
    if not candidates:
        raise FileNotFoundError(f"No {kind.upper()} found under {root}")
    if len(candidates) > 1:
        raise ValueError(
            f"Multiple {kind.upper()} files found; set build.{kind}_path explicitly: "
            + ", ".join(map(str, candidates))
        )
    return candidates[0]


def find_aab(project_dir: Path, configured: str | None = None, module: str = "app") -> Path:
    return _artifact(project_dir, configured, module, "aab")


def find_apk(project_dir: Path, configured: str | None = None, module: str = "app") -> Path:
    return _artifact(project_dir, configured, module, "apk")
