"""Small, explicit Console workflows on the scoped Firefox bridge.

Labels are from the English Console. Unexpected or ambiguous screens stop the flow;
an action response alone never establishes that Google saved a declaration.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .bridge import Client, target_prefix
from .config import load_manifest
from .models import Manifest


class ConsoleSession:
    def __init__(self, client: Client, target: str, timeout: float = 15):
        self.client = client
        self.target = target_prefix(target)
        self.timeout = timeout

    def inspect(self) -> dict:
        return self.client.request("/command", {"operation": "inspect", "target": self.target})

    def wait(self, predicate: Callable[[dict], bool]) -> dict:
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                page = self.inspect()
            except RuntimeError as exc:
                # Only inspection may repeat while a document is being replaced.
                if str(exc) not in {
                    "Could not establish connection. Receiving end does not exist.",
                    "Missing host permission for the tab",
                }:
                    raise
            else:
                if predicate(page):
                    return page
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Expected Console screen did not become ready; inspect before continuing"
                )
            time.sleep(0.3)

    @staticmethod
    def control(page: dict, name: str, tag: str | None = None) -> dict:
        matches = [
            item
            for item in page.get("controls", [])
            if item.get("name") == name and (tag is None or item.get("tag") == tag)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one Console control named {name!r}; found {len(matches)}"
            )
        if matches[0].get("disabled") or matches[0].get("sensitive"):
            raise ValueError(f"Console control {name!r} is disabled or sensitive")
        return matches[0]

    def act(self, name: str, operation: str = "click", value=None, tag: str | None = None) -> dict:
        control = self.control(self.inspect(), name, tag)
        # Mutations are issued once. A timeout must be reconciled by fresh inspection.
        return self.client.request(
            "/command",
            {
                "operation": operation,
                "target": self.target,
                "control_id": control["id"],
                "value": value,
            },
        )

    def open(self, path: str, heading: str, field: str) -> dict:
        url = self.target + path
        if target_prefix(url) != self.target:
            raise ValueError("Console page is outside the selected app")
        navigation = self.client.request(
            "/command", {"operation": "navigate", "target": self.target, "value": url}
        )
        previous = navigation.get("previous_document_id")
        if not previous:
            raise RuntimeError(
                "Reload the temporary Firefox bridge add-on to enable verified navigation"
            )
        return self.wait(
            lambda page: (
                bool(page.get("document_id"))
                and page["document_id"] != previous
                and page.get("url", "").split("?", 1)[0] == url
                and heading in page.get("headings", [])
                and any(
                    item.get("name") == field and not item.get("disabled")
                    for item in page.get("controls", [])
                )
            )
        )


def setup_plan(manifest: Manifest, step: str) -> dict:
    if step == "privacy":
        value = manifest.developer_facts.privacy_policy_url
        if not value or not value.startswith("https://"):
            raise ValueError(
                "Set and review developer_facts.privacy_policy_url as a public HTTPS URL"
            )
        return {
            "step": step,
            "path": "app-content/privacy-policy",
            "heading": "Privacy policy",
            "field": "Privacy policy URL",
            "operation": "fill",
            "value": value,
        }
    if step == "ads":
        value = manifest.developer_facts.contains_ads
        if value is None:
            raise ValueError("Confirm developer_facts.contains_ads before filling the declaration")
        return {
            "step": step,
            "path": "app-content/ads-declaration",
            "heading": "Ads",
            "field": "Yes, my app contains ads" if value else "No, my app does not contain ads",
            "operation": "check",
            "value": True,
        }
    if step == "advertising-id":
        value = manifest.developer_facts.uses_advertising_id
        if value is None:
            raise ValueError(
                "Confirm developer_facts.uses_advertising_id, including third-party SDK use"
            )
        if value:
            raise ValueError(
                "Advertising ID use needs reviewed purpose declarations; this workflow supports No only"
            )
        return {
            "step": step,
            "path": "app-content/ad-id-declaration",
            "heading": "Advertising ID",
            "field": "No",
            "operation": "check",
            "value": True,
        }
    raise ValueError("Supported Console setup steps: privacy, ads, advertising-id")


def apply_setup(manifest_path: Path, step: str, apply: bool = False) -> dict:
    cfg, path = load_manifest(manifest_path)
    plan = setup_plan(cfg, step)
    if not apply:
        return {"status": "preview", "plan": plan, "remote_changes": False}
    if cfg.browser.engine != "firefox" or not cfg.approvals.allow_browser_write_actions:
        raise ValueError(
            "Enable Firefox and approvals.allow_browser_write_actions for Console changes"
        )
    session = ConsoleSession(Client(path), cfg.browser.console_url)
    page = session.open(plan["path"], plan["heading"], plan["field"])

    def matches(page):
        field = session.control(page, plan["field"], "input")
        if plan["operation"] == "fill":
            return field.get("value") == plan["value"]
        return field.get("checked") in (True, "true")

    if not matches(page):
        session.act(plan["field"], plan["operation"], plan["value"], "input")
        session.wait(
            lambda page: any(
                item.get("name") == "Save" and not item.get("disabled")
                for item in page.get("controls", [])
            )
        )
        session.act("Save", tag="button")
        session.wait(
            lambda page: (
                bool(page.get("acknowledgements"))
                or "Go to Publishing overview?" in page.get("headings", [])
            )
        )
        if "Go to Publishing overview?" in session.inspect().get("headings", []):
            session.act("Not now", tag="button")
            session.wait(lambda page: "Go to Publishing overview?" not in page.get("headings", []))
        session.wait(
            lambda page: (
                all(
                    any(
                        item.get("name") == name and item.get("disabled")
                        for item in page.get("controls", [])
                    )
                    for name in ("Save", "Discard")
                )
                and any(
                    item.get("name") == plan["field"] and not item.get("disabled")
                    for item in page.get("controls", [])
                )
            )
        )
    # Reopening the page proves persistence independently of the click response.
    session.open(plan["path"], plan["heading"], plan["field"])
    try:
        page = session.wait(
            lambda page: (
                any(
                    item.get("name") == plan["field"] and not item.get("disabled")
                    for item in page.get("controls", [])
                )
                and matches(page)
            )
        )
    except RuntimeError as exc:
        raise RuntimeError(
            "Console value did not persist after reopening; inspect before retrying"
        ) from exc
    return {"status": "verified", "step": step, "url": page["url"], "final_submission": False}
