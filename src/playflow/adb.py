from __future__ import annotations

from pathlib import Path

from .shell import run


def devices() -> list[str]:
    out = run(["adb", "devices"]).stdout.splitlines()[1:]
    return [parts[0] for line in out if len(parts := line.split()) >= 2 and parts[1] == "device"]


def install(apk: Path, serial: str | None = None) -> str:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["install", "-r", str(apk)]
    return run(cmd).stdout
