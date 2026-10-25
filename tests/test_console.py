import unittest
from itertools import count
from pathlib import Path
from unittest.mock import patch

from playflow.console import ConsoleSession, apply_setup, setup_plan
from playflow.models import Manifest

APP = "https://play.google.com/console/u/0/developers/123/app/42/"


class FakeConsole:
    def __init__(self, persist=True, ambiguous=False, existing=""):
        self.saved = existing
        self.value = existing
        self.persist = persist
        self.ambiguous = ambiguous
        self.document = 1
        self.busy = 0
        self.dirty = False
        self.saved_once = False
        self.calls = []

    def request(self, endpoint, data):
        self.calls.append(data)
        operation = data["operation"]
        if operation == "navigate":
            if self.busy:
                raise AssertionError("Navigation interrupted an in-flight save")
            previous = str(self.document)
            self.document += 1
            self.value = self.saved
            return {"previous_document_id": previous}
        if operation == "fill":
            self.value = data["value"]
            self.dirty = True
        if operation == "click":
            if self.persist:
                self.saved = self.value
            self.busy = 2
            self.dirty = False
            self.saved_once = True
        busy = self.busy > 0
        if operation == "inspect" and busy:
            self.busy -= 1
        controls = [
            {
                "id": "field",
                "tag": "input",
                "name": "Privacy policy URL",
                "value": self.value,
                # Console can leave fields usable while the save is in flight.
                "disabled": False,
            },
            {"id": "save", "tag": "button", "name": "Save", "disabled": not self.dirty},
            {"id": "discard", "tag": "button", "name": "Discard", "disabled": True},
        ]
        if self.ambiguous:
            controls.append(controls[0].copy())
        return {
            "url": APP + "app-content/privacy-policy",
            "document_id": str(self.document),
            "headings": ["Privacy policy"],
            "controls": controls,
            "acknowledgements": ["Change saved"] if self.saved_once and not busy else [],
        }


class ConsoleWorkflowTests(unittest.TestCase):
    def manifest(self):
        return Manifest(
            app_name="Fixture",
            browser={"engine": "firefox", "console_url": APP},
            approvals={"allow_browser_write_actions": True},
            developer_facts={"privacy_policy_url": "https://example.com/privacy"},
        )

    def run_flow(self, client, cfg=None, apply=True):
        with (
            patch(
                "playflow.console.load_manifest",
                return_value=(cfg or self.manifest(), Path("fixture.yaml")),
            ),
            patch("playflow.console.Client", return_value=client),
            patch("playflow.console.time.monotonic", side_effect=count()),
            patch("playflow.console.time.sleep"),
        ):
            return apply_setup(Path("fixture.yaml"), "privacy", apply)

    def test_preview_and_disabled_writes_do_not_connect(self):
        client = FakeConsole()
        self.assertEqual(self.run_flow(client, apply=False)["status"], "preview")
        self.assertEqual(client.calls, [])
        cfg = self.manifest()
        cfg.approvals.allow_browser_write_actions = False
        with self.assertRaisesRegex(ValueError, "Enable Firefox"):
            self.run_flow(client, cfg)
        self.assertEqual(client.calls, [])

    def test_save_is_verified_on_a_new_document(self):
        client = FakeConsole()
        self.assertEqual(self.run_flow(client)["status"], "verified")
        self.assertEqual([call["operation"] for call in client.calls].count("click"), 1)
        self.assertEqual([call["operation"] for call in client.calls].count("navigate"), 2)
        self.assertEqual(client.saved, "https://example.com/privacy")

    def test_existing_value_is_reopened_without_resaving(self):
        client = FakeConsole(existing="https://example.com/privacy")
        self.assertEqual(self.run_flow(client)["status"], "verified")
        self.assertFalse(any(call["operation"] == "click" for call in client.calls))

    def test_failed_persistence_is_reported_without_retrying_the_write(self):
        client = FakeConsole(persist=False)
        with self.assertRaisesRegex(RuntimeError, "did not persist"):
            self.run_flow(client)
        self.assertEqual([call["operation"] for call in client.calls].count("click"), 1)

    def test_ambiguous_fields_stop_before_mutation(self):
        client = FakeConsole(ambiguous=True)
        with self.assertRaisesRegex(ValueError, "found 2"):
            self.run_flow(client)
        self.assertFalse(any(call["operation"] in {"fill", "click"} for call in client.calls))

    def test_missing_declarations_cannot_be_guessed(self):
        cfg = Manifest(app_name="Fixture")
        for step in ("ads", "privacy", "advertising-id", "unknown"):
            with self.subTest(step=step), self.assertRaises(ValueError):
                setup_plan(cfg, step)
        cfg.developer_facts.contains_ads = False
        self.assertEqual(setup_plan(cfg, "ads")["field"], "No, my app does not contain ads")
        cfg.developer_facts.uses_advertising_id = True
        with self.assertRaisesRegex(ValueError, "purpose declarations"):
            setup_plan(cfg, "advertising-id")
        cfg.developer_facts.uses_advertising_id = False
        self.assertEqual(setup_plan(cfg, "advertising-id")["field"], "No")

    def test_navigation_requires_document_replacement(self):
        class StaleClient(FakeConsole):
            def request(self, endpoint, data):
                if data["operation"] == "navigate":
                    return {"previous_document_id": str(self.document)}
                return super().request(endpoint, data)

        session = ConsoleSession(StaleClient(), APP, timeout=0)
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            session.open("app-content/privacy-policy", "Privacy policy", "Privacy policy URL")

    def test_unknown_write_outcome_is_not_retried(self):
        class FailedClient(FakeConsole):
            def request(self, endpoint, data):
                if data["operation"] == "click":
                    self.calls.append(data)
                    raise RuntimeError("outcome unknown")
                return super().request(endpoint, data)

        client = FailedClient()
        with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
            self.run_flow(client)
        self.assertEqual([call["operation"] for call in client.calls].count("click"), 1)

    def test_disabled_save_button_without_acknowledgement_does_not_trigger_reload(self):
        class NoAcknowledgement(FakeConsole):
            def request(self, endpoint, data):
                page = super().request(endpoint, data)
                page.pop("acknowledgements", None)
                return page

        client = NoAcknowledgement()
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            self.run_flow(client)
        self.assertEqual([call["operation"] for call in client.calls].count("navigate"), 1)

    def test_saved_overview_dialog_is_dismissed_before_reopening(self):
        class SavedDialog(FakeConsole):
            popup = False

            def request(self, endpoint, data):
                if data["operation"] == "navigate" and self.popup:
                    raise AssertionError("Saved dialog was not handled")
                if data["operation"] == "click" and data.get("control_id") == "not-now":
                    self.calls.append(data)
                    self.popup = False
                    return self.request(endpoint, {"operation": "inspect"})
                page = super().request(endpoint, data)
                if data["operation"] == "click":
                    self.popup = True
                page["acknowledgements"] = []
                if self.popup and not self.busy:
                    page["headings"].append("Go to Publishing overview?")
                    page["controls"].append({"id": "not-now", "name": "Not now", "tag": "button"})
                return page

        client = SavedDialog()
        self.assertEqual(self.run_flow(client)["status"], "verified")
        self.assertEqual(sum(call.get("control_id") == "not-now" for call in client.calls), 1)
