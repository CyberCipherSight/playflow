import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from playflow.browser import _change, _console_url, _locate, _sensitive, replay_recording


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.recording = Path(self.temp.name) / "recording.json"

    def write(self, data):
        self.recording.write_text(json.dumps(data))

    def test_list_recordings_preview_without_browser_or_profile(self):
        self.write([{"event": "navigation", "url": "https://play.google.com/console/"}])
        profile = Path(self.temp.name) / "profile"
        with patch("playflow.browser._context") as context:
            result = replay_recording(str(profile), self.recording)
        context.assert_not_called()
        self.assertFalse(profile.exists())
        self.assertEqual(result[0]["skipped"], "offline preview")

    def test_unsafe_navigation_rejected_before_browser_start(self):
        for url in (
            "https://evil.example/console/",
            "https://play.google.com.evil/console/",
            "file:///etc/passwd",
            "https://play.google.com/console/?token=private",
            "https://play.google.com/console-other",
            "https://user@play.google.com/console/",
        ):
            with self.subTest(url=url), patch("playflow.browser._context") as context:
                self.write({"events": [{"event": "navigation", "url": url}]})
                with self.assertRaises(ValueError):
                    replay_recording("unused", self.recording, allow_write=True)
                context.assert_not_called()

    def test_recording_shape_and_version_validation(self):
        for data in (
            {"schema_version": 2, "events": []},
            {"events": [None]},
            [],
            {"events": [{"element": None}]},
            "wrong",
        ):
            self.write(data)
            if data == []:
                self.assertEqual(replay_recording("unused", self.recording), [])
            else:
                with self.subTest(data=data), self.assertRaises(ValueError):
                    replay_recording("unused", self.recording)

    def test_checkbox_can_be_unchecked_and_select_can_be_selected(self):
        locator = Mock()
        _change(locator, {"element": {"type": "checkbox"}, "value": False})
        locator.set_checked.assert_called_once_with(False, timeout=7000)
        _change(locator, {"element": {"tag": "select"}, "value": "internal"})
        locator.select_option.assert_called_once_with("internal", timeout=7000)

    def test_sensitive_events_never_replayed(self):
        for event in (
            {"value": "[REDACTED]"},
            {"element": {"type": "file"}},
            {"element": {"autocomplete": "one-time-code"}},
            {"element": {"sensitive": True}},
        ):
            with self.subTest(event=event):
                self.assertTrue(_sensitive(event))

    def test_ambiguous_locator_does_not_choose_first(self):
        page = Mock()
        page.get_by_role.return_value.count.return_value = 2
        with self.assertRaises(ValueError):
            _locate(page, {"role": "button", "name": "Submit"})

    def test_missing_semantic_locator_falls_back_to_label(self):
        page = Mock()
        page.get_by_role.return_value.count.return_value = 0
        page.get_by_label.return_value.count.return_value = 1
        self.assertIs(
            _locate(page, {"role": "textbox", "name": "Name", "label": "Name"}),
            page.get_by_label.return_value,
        )

    def test_delayed_control_waits_before_failing(self):
        page = Mock()
        locator = page.get_by_role.return_value
        locator.count.side_effect = [0, 1]
        self.assertIs(_locate(page, {"role": "button", "name": "Save"}), locator)
        locator.wait_for.assert_called_once_with(state="visible", timeout=2000)

    def test_replay_stops_after_first_failed_action_and_closes_context(self):
        self.write(
            {"events": [{"event": "click", "element": {"role": "button", "name": "Submit"}}] * 2}
        )
        context = MagicMock()
        page = context.__enter__.return_value.pages[0]
        page.url = "https://play.google.com/console/"
        with (
            patch("playflow.browser._context", return_value=context),
            patch("playflow.browser._locate", side_effect=ValueError("secret")) as locate,
        ):
            results = replay_recording("unused", self.recording, allow_write=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["error"], "ValueError")
        self.assertEqual(locate.call_count, 1)
        context.__exit__.assert_called_once()

    def test_console_url_restriction(self):
        self.assertTrue(_console_url("https://play.google.com/console/developers/123"))
        self.assertFalse(_console_url("https://accounts.google.com/"))
