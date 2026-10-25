import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

from playflow.bridge import Job, Session, handler, target_prefix

APP = "https://play.google.com/console/u/0/developers/123/app/42/"
SITE = "https://sites.google.com/d/site-id/"


class BridgeScopeTests(unittest.TestCase):
    def test_actual_app_and_site_are_scoped_independently(self):
        self.assertEqual(target_prefix(APP + "app-dashboard"), APP)
        self.assertEqual(target_prefix(SITE + "p/page-id/edit"), SITE)
        for value in (
            "https://play.google.com/console/",
            "https://evil.example/",
            APP + "x?token=x",
            APP + "../43/",
            APP + "%2e%2e/43/",
            None,
            "https://user@sites.google.com/d/site-id/",
            "file:///tmp/x",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                target_prefix(value)

    def session(self, write=True):
        session = Session([APP], write)
        session.snapshots[APP] = {"controls": [{"id": "revision:0", "name": "Privacy policy"}]}
        return session

    def test_writes_are_gated_but_inspection_is_allowed(self):
        session = self.session(False)
        self.assertEqual(session.validate({"operation": "inspect", "target": APP})["target"], APP)
        with self.assertRaisesRegex(ValueError, "disabled in the manifest"):
            session.validate({"operation": "click", "target": APP, "control_id": "revision:0"})

    def test_wrong_app_and_stale_controls_are_rejected(self):
        session = self.session()
        for payload in (
            {"operation": "inspect", "target": APP.replace("/42/", "/420/")},
            {"operation": "click", "target": APP, "control_id": "old:0"},
            {"operation": "navigate", "target": APP, "value": APP + "../420/"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                session.validate(payload)

    def test_final_submission_and_sensitive_controls_are_blocked(self):
        session = self.session()
        for control in (
            {"id": "revision:0", "name": "Send changes for review"},
            {"id": "revision:0", "name": "Submit 15 changes for review"},
            {"id": "revision:0", "name": "Publish"},
            {"id": "revision:0", "name": "Password", "sensitive": True},
            {"id": "revision:0", "name": "Save", "disabled": True},
        ):
            session.snapshots[APP]["controls"] = [control]
            with self.subTest(control=control), self.assertRaises(ValueError):
                session.validate({"operation": "click", "target": APP, "control_id": "revision:0"})

    def test_field_types_are_checked(self):
        session = self.session()
        for operation, value in (("fill", False), ("check", "false"), ("select", None)):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                session.validate(
                    {
                        "operation": operation,
                        "target": APP,
                        "control_id": "revision:0",
                        "value": value,
                    }
                )

    def test_site_publish_requires_its_own_bounded_session_authorization(self):
        session = Session([APP, SITE], True, allow_site_publish=True)
        for target in (APP, SITE):
            session.snapshots[target] = {"controls": [{"id": "publish:0", "name": "Publish"}]}
        payload = {"operation": "click", "control_id": "publish:0"}
        with self.assertRaisesRegex(ValueError, "Final submission"):
            session.validate({**payload, "target": APP})
        for _ in range(2):
            self.assertTrue(session.validate({**payload, "target": SITE})["approved_site_publish"])
        with self.assertRaisesRegex(ValueError, "Final submission"):
            session.validate({**payload, "target": SITE})
        unapproved = Session([SITE], True)
        unapproved.snapshots[SITE] = session.snapshots[SITE]
        with self.assertRaisesRegex(ValueError, "Final submission"):
            unapproved.validate({**payload, "target": SITE})

    def test_review_permission_is_bound_to_app_page_count_and_confirmation(self):
        session = Session([APP, SITE], True, approved_review_changes=15)
        control = {"id": "review:0", "name": "Submit 15 changes for review"}
        session.snapshots[APP] = {"url": APP + "publishing", "controls": [control]}
        payload = {"operation": "click", "target": APP, "control_id": "review:0"}
        for name in (
            "Submit 16 changes for review",
            "Submit changes for review",
            "Publish",
            "Start rollout",
        ):
            control["name"] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                session.validate(payload)
        control["name"] = "Submit 15 changes for review"
        session.snapshots[APP]["url"] = APP + "app-dashboard"
        with self.assertRaises(ValueError):
            session.validate(payload)
        session.snapshots[APP]["url"] = APP + "publishing"
        self.assertEqual(session.validate(payload)["approved_play_review"], 15)
        with self.assertRaises(ValueError):
            session.validate(payload)  # Cannot repeat the counted submission button.
        control["name"] = "Submit changes for review"
        self.assertEqual(session.validate(payload)["approved_play_review"], 15)
        with self.assertRaises(ValueError):
            session.validate(payload)

    def test_single_change_approval_remains_counted_and_one_use(self):
        session = Session([APP], True, approved_review_changes=1)
        control = {"id": "review:0", "name": "Submit 1 change for review"}
        session.snapshots[APP] = {"url": APP + "publishing", "controls": [control]}
        payload = {"operation": "click", "target": APP, "control_id": "review:0"}
        control["name"] = "Submit 2 changes for review"
        with self.assertRaises(ValueError):
            session.validate(payload)
        control["name"] = "Submit 1 change for review"
        self.assertEqual(session.validate(payload)["approved_play_review"], 1)
        with self.assertRaises(ValueError):
            session.validate(payload)
        control["name"] = "Send change for review"
        self.assertEqual(session.validate(payload)["approved_play_review"], 1)
        with self.assertRaises(ValueError):
            session.validate(payload)

    def test_expired_queued_command_is_never_dispatched(self):
        session = self.session()
        job = Job({"id": "old", "deadline": 0})
        session.pending.append(job)
        self.assertIsNone(session.next_job())
        self.assertTrue(job.done.is_set())
        self.assertIn("expired", job.result["error"])

    def test_extension_result_updates_controls_after_each_action(self):
        session = self.session()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(session.command, {"operation": "inspect", "target": APP})
            with session.condition:
                self.assertTrue(
                    session.condition.wait_for(lambda: bool(session.pending), timeout=2)
                )
            payload = session.next_job()
            snapshot = {
                "url": APP + "app-content/privacy-policy?source=dashboard",
                "controls": [{"id": "new:0", "name": "Save"}],
            }
            session.complete({"id": payload["id"], "result": snapshot})
            self.assertEqual(future.result(timeout=2), snapshot)
        with self.assertRaisesRegex(ValueError, "stale"):
            session.validate({"operation": "click", "target": APP, "control_id": "revision:0"})
        self.assertEqual(session.snapshots[APP], snapshot)


class BridgeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.session = Session([APP], False)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.session))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, headers):
        return self.opener.open(
            urllib.request.Request(self.url + "/status", headers=headers), timeout=2
        )

    def test_no_status_or_page_information_without_token(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get({})
        self.assertEqual(error.exception.code, 401)
        self.assertNotIn(self.session.token, error.exception.read().decode())
        error.exception.close()

    def test_web_origin_and_rebound_host_are_rejected_even_with_token(self):
        auth = {"Authorization": "Bearer " + self.session.token}
        for extra in ({"Origin": "https://play.google.com"}, {"Host": "evil.example"}):
            with self.subTest(extra=extra), self.assertRaises(urllib.error.HTTPError) as error:
                self.get({**auth, **extra})
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_authenticated_extension_can_check_connection_without_secret_disclosure(self):
        self.session.last_seen = time.monotonic()
        with self.get(
            {"Authorization": "Bearer " + self.session.token, "Origin": "moz-extension://fixture"}
        ) as response:
            data = json.load(response)
        self.assertTrue(data["connected"])
        self.assertEqual(data["targets"], [APP])
        self.assertNotIn(self.session.token, json.dumps(data))
