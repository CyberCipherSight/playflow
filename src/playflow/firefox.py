"""Read Firefox profile metadata and request navigation without controlling forms."""

from __future__ import annotations

import configparser
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from .urls import is_console_url


def _profile_roots() -> list[Path]:
    home = Path.home()
    roots = [
        Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "mozilla/firefox",
        home / ".mozilla/firefox",
        home / "snap/firefox/common/.mozilla/firefox",
        home / ".var/app/org.mozilla.firefox/.mozilla/firefox",
        home / "Library/Application Support/Firefox",
    ]
    if os.environ.get("APPDATA"):
        roots.append(Path(os.environ["APPDATA"]) / "Mozilla/Firefox")
    return list(dict.fromkeys(root.expanduser().resolve() for root in roots))


def profiles(roots: list[Path] | None = None) -> list[dict]:
    """Read only names and paths from legacy registries and selectable-profile DBs."""
    result = []
    for root in roots if roots is not None else _profile_roots():
        registry = root / "profiles.ini"
        if registry.is_file():
            config = configparser.ConfigParser(interpolation=None)
            try:
                config.read(registry, encoding="utf-8")
                for section in config.sections():
                    if not section.startswith("Profile"):
                        continue
                    entry = config[section]
                    if not entry.get("Name") or not entry.get("Path"):
                        continue
                    path = Path(entry["Path"])
                    if entry.get("IsRelative", "1") == "1":
                        path = root / path
                    result.append(
                        {
                            "name": entry["Name"],
                            "path": str(path.resolve()),
                            "source": str(registry),
                        }
                    )
            except configparser.Error as exc:
                raise ValueError(f"Cannot parse Firefox profile registry: {registry}") from exc
        for database in sorted((root / "Profile Groups").glob("*.sqlite")):
            try:
                with closing(
                    sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
                ) as db:
                    rows = db.execute('SELECT name, path FROM "Profiles"').fetchall()
                for name, relative in rows:
                    result.append(
                        {
                            "name": name,
                            "path": str((root / relative).resolve()),
                            "source": str(database),
                        }
                    )
            except sqlite3.Error as exc:
                raise RuntimeError(f"Cannot read Firefox profile database: {database}") from exc
    unique = {(entry["name"], entry["path"]): entry for entry in result}
    return sorted(unique.values(), key=lambda entry: (entry["name"].casefold(), entry["path"]))


def resolve_profile(name: str | None, path: str | None = None) -> Path:
    if path:
        selected = Path(path).expanduser().resolve()
    else:
        registered = profiles()
        matches = {Path(entry["path"]) for entry in registered if entry["name"] == name}
        if not matches and name:
            matches = {
                Path(entry["path"])
                for entry in registered
                if entry["name"].casefold() == name.casefold()
            }
        if len(matches) != 1:
            available = ", ".join(sorted({entry["name"] for entry in registered})) or "none"
            raise ValueError(
                f"Firefox profile {name!r} is missing or ambiguous. Available: {available}. "
                "Set browser.firefox_profile_path to its exact existing directory."
            )
        selected = matches.pop()
    if not selected.is_dir() or not (selected / "prefs.js").is_file():
        raise ValueError(f"Not an existing initialized Firefox profile: {selected}")
    return selected


def open_console(url: str, name: str | None, path: str | None = None) -> dict:
    if not is_console_url(url):
        raise ValueError("Use an HTTPS Play Console URL without query parameters or fragment")
    selected = resolve_profile(name, path)
    executable = shutil.which("firefox")
    if not executable:
        raise RuntimeError("Firefox was not found on PATH")
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        raise RuntimeError(
            "No desktop display is available; run open-console from your desktop terminal"
        )
    # Never copy cookies, enable remote debugging, create a profile or clear a lock.
    process = subprocess.Popen(
        [executable, "--profile", str(selected), "--new-tab", url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
    )
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        code = None  # A new GUI process can stay alive until the user closes Firefox.
    if code not in (None, 0):
        reason = f"terminated by signal {-code}" if code < 0 else f"exited with code {code}"
        raise RuntimeError(
            f"Firefox {reason}. Run open-console from your normal desktop terminal; "
            "this session may block desktop/profile access."
        )
    return {
        "status": "launch_requested",
        "profile_path": str(selected),
        "url": url,
        "page_verified": False,
    }
