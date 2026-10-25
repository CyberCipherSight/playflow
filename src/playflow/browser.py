from __future__ import annotations

import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .urls import PLAY_CONSOLE
from .urls import is_console_url as _console_url

SENSITIVE = re.compile(
    r"pass(word)?|token|secret|csrf|auth|session|cookie|otp|one[- ]?time|verification|"
    r"card|cvv|cvc|iban|account.?number",
    re.I,
)
REDACTED = {"[REDACTED]", "[FILE_SELECTED]", "[OMITTED]"}


def _profile(path: str) -> Path:
    profile = Path(path).expanduser().resolve()
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    return profile


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Browser actions need: pip install 'playflow[browser]' && playwright install chromium"
        ) from exc
    return sync_playwright()


@contextmanager
def _context(profile_path: str) -> Iterator[Any]:
    with _playwright() as playwright:
        ctx = playwright.chromium.launch_persistent_context(
            str(_profile(profile_path)), headless=False
        )
        try:
            yield ctx
        finally:
            ctx.close()


def authenticate(profile_path: str) -> None:
    with _context(profile_path) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PLAY_CONSOLE)
        print(
            "Complete Google sign-in / 2FA. Return here and press Enter when Play Console is open."
        )
        input()


def doctor(profile_path: str) -> dict:
    with _context(profile_path) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PLAY_CONSOLE, wait_until="domcontentloaded")
        return {"url": page.url, "title": page.title(), "console_reachable": _console_url(page.url)}


def _locate(page: Any, element: dict):
    name = element.get("name") or element.get("label") or element.get("text")
    candidates = []
    if element.get("role") and name:
        candidates.append(page.get_by_role(element["role"], name=name, exact=True))
    if element.get("label"):
        candidates.append(page.get_by_label(element["label"], exact=True))
    if element.get("text"):
        candidates.append(page.get_by_text(element["text"], exact=True))
    if element.get("selector"):
        candidates.append(page.locator(element["selector"]))
    for locator in candidates:
        count = locator.count()
        if count == 0:
            try:
                locator.wait_for(state="visible", timeout=2000)
            except Exception:
                continue
            count = locator.count()
        if count > 1:
            raise ValueError("Ambiguous recorded control; update the recording")
        if count == 1:
            return locator
    raise ValueError("Recorded control not found")


def _events(recording: Path) -> list[dict]:
    data = json.loads(recording.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if data.get("schema_version", 1) != 1:
            raise ValueError("Unsupported recording schema version")
        events = data.get("events")
    else:
        events = data
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("Recording must contain a list of event objects")
    for event in events:
        if not isinstance(event.get("element", {}), dict):
            raise ValueError("Recorded element must be an object")
        if event.get("event") == "navigation":
            if not isinstance(event.get("url"), str) or not _console_url(event["url"]):
                raise ValueError(
                    "Recording navigation must use a Play Console URL without query or fragment"
                )
    return events


def _sensitive(event: dict) -> bool:
    element = event.get("element", {})
    metadata = " ".join(
        str(element.get(key, ""))
        for key in (
            "name",
            "label",
            "name_attr",
            "autocomplete",
            "selector",
        )
    )
    value = event.get("value")
    return bool(
        element.get("sensitive")
        or element.get("type") in {"password", "file", "hidden"}
        or SENSITIVE.search(metadata)
        or (isinstance(value, str) and value in REDACTED)
    )


def _change(locator: Any, event: dict) -> None:
    element = event.get("element", {})
    value = event.get("value")
    if element.get("type") in {"radio", "checkbox"} or element.get("role") in {"radio", "checkbox"}:
        if not isinstance(value, bool):
            raise ValueError("Checkbox/radio changes require a boolean value")
        locator.set_checked(value, timeout=7000)
    elif element.get("tag") == "select":
        locator.select_option(value, timeout=7000)
    elif isinstance(value, str):
        locator.fill(value, timeout=7000)
    else:
        raise ValueError("Unsupported recorded change value")


def replay_recording(
    profile_path: str,
    recording: Path,
    allow_write: bool = False,
    max_events: int | None = None,
) -> list[dict]:
    if max_events is not None and max_events < 1:
        raise ValueError("max_events must be positive")
    events = _events(recording)
    if max_events is not None:
        events = events[:max_events]
    if not allow_write:
        # The default preview never opens an authenticated browser or follows URLs.
        return [{"event": event.get("event"), "skipped": "offline preview"} for event in events]
    results: list[dict] = []
    with _context(profile_path) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def guard(route):
            request = route.request
            if request.is_navigation_request() and not _console_url(request.url):
                route.abort()
            else:
                route.continue_()

        ctx.route("**/*", guard)
        page.goto(PLAY_CONSOLE, wait_until="domcontentloaded")
        for event in events:
            kind = event.get("event")
            if kind not in {"navigation", "click", "change"} or _sensitive(event):
                results.append({"event": kind, "skipped": "unsupported or sensitive event"})
                continue
            try:
                if kind == "navigation":
                    page.goto(event["url"], wait_until="domcontentloaded")
                else:
                    if not _console_url(page.url):
                        raise ValueError("Authenticate with playflow auth before replay")
                    locator = _locate(page, event.get("element", {}))
                    if kind == "click":
                        locator.click(timeout=7000)
                    else:
                        _change(locator, event)
                results.append({"event": kind, "ok": True})
            except Exception as exc:
                # Stop at the first failure; later steps may otherwise submit wrong facts.
                results.append({"event": kind, "ok": False, "error": type(exc).__name__})
                break
    return results
