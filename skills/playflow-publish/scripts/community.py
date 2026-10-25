"""Local opt-in preference for contribution proposals; no network or Git operations."""

from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
from pathlib import Path

MODES = {"ask", "off", "review"}


def config_path(environ=None, system=None) -> Path:
    env = os.environ if environ is None else environ
    target = platform.system() if system is None else system
    if target == "Windows":
        base = (
            Path(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else Path.home() / "AppData/Local"
        )
    else:
        base = (
            Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else Path.home() / ".config"
        )
        if not base.is_absolute():
            base = Path.home() / ".config"
    return base / "playflow/community.json"


def read_mode(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("Contribution preference must be a regular local file")
    if not path.exists():
        return "ask"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Invalid contribution preference file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Cannot read contribution preference; no sharing is authorized") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "mode"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["mode"], str)
        or value["mode"] not in MODES
    ):
        raise ValueError("Unsupported contribution preference; no sharing is authorized")
    return value["mode"]


def save_mode(path: Path, mode: str) -> None:
    if mode not in MODES:
        raise ValueError("Mode must be ask, off, or review")
    # Refuse malformed or linked state rather than silently treating it as consent.
    read_mode(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".community-", delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump({"schema_version": 1, "mode": mode}, output)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def status(mode: str) -> dict:
    return {
        "schema_version": 1,
        "mode": mode,
        "offer_onboarding": mode == "ask",
        "prepare_proposals": mode == "review",
        "github_write_authorized": False,
        "approval_required_for_each_proposal": True,
        "scope": "Local preference only; no telemetry, GitHub calls, uploads, or credentials.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Explicit local preference file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    setter = sub.add_parser("set")
    setter.add_argument("mode", choices=sorted(MODES))
    args = parser.parse_args(argv)
    path = args.config.expanduser() if args.config else config_path()
    try:
        if args.command == "set":
            save_mode(path, args.mode)
        print(json.dumps(status(read_mode(path)), indent=2))
    except (OSError, ValueError):
        # Do not echo file contents or local account paths in error output.
        print(json.dumps({"error": "Preference unavailable or invalid; no sharing is authorized."}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
