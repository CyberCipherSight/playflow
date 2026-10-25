"""Authenticated loopback connection to the user's temporary Firefox extension."""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import load_manifest
from .signing import _private_new_file
from .urls import is_console_url

MAX_BODY = 1024 * 1024
FINAL_ACTION = re.compile(
    r"publish|roll\s*out|(?:send|submit).*review|start.*rollout|delete.*app|remove.*app", re.I
)
OPERATIONS = {"inspect", "click", "fill", "check", "select", "navigate", "attach"}
REVIEW_ACTION = re.compile(r"^(?:Submit|Send)(?: (\d+))?(?: changes?)? for review$")


def target_prefix(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("Bridge target must be a URL string")
    parsed = urlsplit(url)
    if "\\" in url or any(part in {".", ".."} for part in unquote(parsed.path).split("/")):
        raise ValueError("Bridge target must not contain path traversal")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("Bridge targets must omit credentials, query parameters and fragments")
    if is_console_url(url):
        match = re.match(r"(/console/u/\d+/developers/\d+/app/\d+/)", parsed.path)
    elif parsed.scheme == "https" and parsed.netloc == "sites.google.com":
        match = re.match(r"(/d/[A-Za-z0-9_-]+/)", parsed.path)
    else:
        match = None
    if not match:
        raise ValueError(
            "Use the actual app's Console URL or an explicitly selected Google Sites editor URL"
        )
    return f"https://{parsed.netloc}{match[1]}"


@dataclass
class Job:
    payload: dict
    done: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    claimed: bool = False


class Session:
    def __init__(
        self,
        targets: list[str],
        allow_write: bool,
        uploads: dict | None = None,
        allow_site_publish: bool = False,
        approved_review_changes: int | None = None,
    ):
        self.token = secrets.token_urlsafe(48)
        self.targets = targets
        self.allow_write = allow_write
        self.uploads = uploads or {}
        self.site_publish_remaining = 2 if allow_site_publish else 0
        if approved_review_changes is not None and approved_review_changes <= 0:
            raise ValueError("Approved review change count must be positive")
        self.review_change_count = approved_review_changes
        self.review_actions_remaining = 2 if approved_review_changes is not None else 0
        self.condition = threading.Condition()
        self.pending: deque[Job] = deque()
        self.active: Job | None = None
        self.last_seen = 0.0
        self.snapshots: dict[str, dict] = {}

    def validate(self, data: dict) -> dict:
        operation = data.get("operation")
        if operation not in OPERATIONS:
            raise ValueError("Unknown bridge operation")
        target = target_prefix(data.get("target", ""))
        if target not in self.targets:
            raise ValueError("Target is outside this session's configured scope")
        if operation != "inspect" and not self.allow_write:
            raise ValueError("Browser actions are disabled in the manifest")
        if operation == "navigate":
            value = data.get("value", "")
            if target_prefix(value) != target:
                raise ValueError("Navigation outside the selected app/site is forbidden")
        elif operation != "inspect":
            snapshot = self.snapshots.get(target, {})
            control = next(
                (
                    item
                    for item in snapshot.get("controls", [])
                    if item["id"] == data.get("control_id")
                ),
                None,
            )
            if not control:
                raise ValueError("Unknown or stale control; inspect the page before acting")
            attachment = operation == "attach" and control.get("type") == "file"
            if control.get("disabled") or (control.get("sensitive") and not attachment):
                raise ValueError("Sensitive or disabled control cannot be automated")
            if operation == "attach":
                if not attachment or data.get("asset") not in self.uploads:
                    raise ValueError(
                        "Attach requires a file input and an explicitly configured upload"
                    )
                if not target.startswith("https://play.google.com/"):
                    raise ValueError(
                        "Release attachments are restricted to the selected Console app"
                    )
            site_publish = (
                operation == "click"
                and target.startswith("https://sites.google.com/d/")
                and control.get("name") == "Publish"
                and self.site_publish_remaining > 0
            )
            review_match = REVIEW_ACTION.fullmatch(control.get("name", ""))
            review_publish = (
                operation == "click"
                and target.startswith("https://play.google.com/")
                and urlsplit(snapshot.get("url", "")).path == urlsplit(target + "publishing").path
                and review_match is not None
                and self.review_actions_remaining > 0
                and (
                    (
                        self.review_actions_remaining == 2
                        and review_match[1] is not None
                        and int(review_match[1]) == self.review_change_count
                    )
                    or (review_match[1] is None and self.review_actions_remaining == 1)
                )
            )
            if FINAL_ACTION.search(control.get("name", "")) and not (
                site_publish or review_publish
            ):
                raise ValueError("Final submission requires a separate reviewed action")
            if operation in {"fill", "select"} and not isinstance(data.get("value"), str):
                raise ValueError("Text and select operations require a string value")
            if operation == "check" and not isinstance(data.get("value"), bool):
                raise ValueError("Checkbox operations require a boolean value")
        result = {
            "id": uuid.uuid4().hex,
            "operation": operation,
            "target": target,
            "control_id": data.get("control_id"),
            "value": data.get("value"),
            "deadline": int((time.time() + 25) * 1000),
        }
        if operation == "attach":
            result["file"] = self.uploads[data["asset"]]
        if operation == "click" and site_publish:
            self.site_publish_remaining -= 1
            result["approved_site_publish"] = True
        if operation == "click" and review_publish:
            self.review_actions_remaining -= 1
            result["approved_play_review"] = self.review_change_count
        return result

    def command(self, data: dict) -> dict:
        with self.condition:
            if self.active and self.active.payload["deadline"] < int(time.time() * 1000):
                if data.get("operation") != "inspect":
                    raise ValueError("Previous command outcome is unknown; inspect before acting")
                self.active = None
                self.snapshots.clear()
            if self.active or self.pending:
                raise ValueError("Another browser command is active; inspect after it finishes")
            job = Job(self.validate(data))
            self.pending.append(job)
            self.condition.notify_all()
        if not job.done.wait(25):
            with self.condition:
                if job in self.pending:
                    self.pending.remove(job)
            raise RuntimeError(
                "Browser command timed out. Its outcome may be unknown; inspect before retrying."
            )
        return job.result or {"error": "Empty extension response"}

    def next_job(self) -> dict | None:
        with self.condition:
            self.last_seen = time.monotonic()
            if not self.pending:
                self.condition.wait(4)
            if not self.pending:
                return None
            self.active = self.pending.popleft()
            if self.active.payload["deadline"] < int(time.time() * 1000):
                self.active.result = {"error": "Command expired before dispatch"}
                self.active.done.set()
                self.active = None
                return None
            self.active.claimed = True
            return self.active.payload

    def complete(self, data: dict) -> None:
        with self.condition:
            job = self.active
            if not job or data.get("id") != job.payload["id"]:
                raise ValueError("Unexpected command result")
            result = data.get("result")
            if not isinstance(result, dict):
                raise ValueError("Extension result must be an object")
            if "controls" in result:
                # Console task links add routing metadata such as ?source=dashboard.
                # Scope remains the selected app/site path, independently of that metadata.
                page_url = urlsplit(result.get("url", ""))
                page_scope = target_prefix(page_url._replace(query="", fragment="").geturl())
                if page_scope != job.payload["target"]:
                    raise ValueError("Extension result came from outside the selected scope")
                self.snapshots[job.payload["target"]] = result
            elif job.payload["operation"] != "inspect":
                self.snapshots.pop(job.payload["target"], None)
            job.result = result
            self.active = None
            job.done.set()


def handler(session: Session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log request bodies, authorization headers or page values.

        def respond(self, status: int, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self) -> bool:
            origin = self.headers.get("Origin", "")
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected_host or (
                origin and urlsplit(origin).scheme != "moz-extension"
            ):
                self.respond(403, {"error": "Invalid local request origin"})
                return False
            value = self.headers.get("Authorization", "")
            if not hmac.compare_digest(value.encode(), ("Bearer " + session.token).encode()):
                self.respond(401, {"error": "Bridge authentication required"})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == "/next":
                self.respond(200, session.next_job())
            elif self.path == "/status":
                self.respond(
                    200,
                    {
                        "connected": bool(
                            session.last_seen and time.monotonic() - session.last_seen < 10
                        ),
                        "targets": session.targets,
                        "allow_write": session.allow_write,
                        "command_active": session.active is not None,
                        "site_publish_actions_remaining": session.site_publish_remaining,
                        "review_submission_actions_remaining": session.review_actions_remaining,
                        "uploads": {
                            key: {field: value for field, value in asset.items() if field != "data"}
                            for key, asset in session.uploads.items()
                        },
                    },
                )
            else:
                self.respond(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_BODY:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Request body must be an object")
                if self.path == "/command":
                    self.respond(200, session.command(data))
                elif self.path == "/result":
                    session.complete(data)
                    self.respond(200, {"ok": True})
                else:
                    self.respond(404, {"error": "Unknown endpoint"})
            except (ValueError, RuntimeError) as exc:
                self.respond(400, {"error": str(exc)})

    return Handler


def locator(manifest: Path) -> Path:
    cfg, path = load_manifest(manifest)
    state = cfg.resolved_state_dir(path) or cfg.resolved_project_dir(path) / ".playflow"
    return state / "browser-bridge.json"


def serve(
    manifest: Path,
    sites: list[str] | None = None,
    *,
    allow_site_publish: bool = False,
    approved_review_changes: int | None = None,
) -> None:
    from .attachments import capture_uploads

    cfg, manifest_path = load_manifest(manifest)
    if allow_site_publish and not sites:
        raise ValueError("Site publishing requires an explicitly selected --site-url")
    if cfg.browser.engine != "firefox":
        raise ValueError("The bridge requires browser.engine: firefox")
    targets = list(
        dict.fromkeys(target_prefix(url) for url in [cfg.browser.console_url, *(sites or [])])
    )
    uploads = capture_uploads(cfg, cfg.resolved_project_dir(manifest_path))
    session = Session(
        targets,
        cfg.approvals.allow_browser_write_actions,
        uploads,
        allow_site_publish,
        approved_review_changes,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(session))
    private_root = Path.home() / ".config/playflow"
    private_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix="firefox-bridge-", dir=private_root))
    extension = runtime / "extension"
    extension.mkdir(mode=0o700)
    for asset in (Path(__file__).parent / "browser_extension").iterdir():
        if asset.name != "config.js" and asset.is_file():
            shutil.copyfile(asset, extension / asset.name)
    connection = {"url": f"http://127.0.0.1:{server.server_port}", "token": session.token}
    credentials = runtime / "connection.json"
    _private_new_file(credentials, json.dumps(connection))
    _private_new_file(
        extension / "config.js",
        "globalThis.PlayFlowBridgeConfig = "
        + json.dumps({**connection, "targets": targets})
        + ";\n",
    )
    location = locator(manifest_path)
    location.parent.mkdir(parents=True, exist_ok=True)
    try:
        with location.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "credentials_file": str(credentials),
                    "extension_manifest": str(extension / "manifest.json"),
                },
                stream,
            )
    except BaseException:
        server.server_close()
        raise
    print(f"Load this temporary Firefox add-on: {extension / 'manifest.json'}", flush=True)
    print(
        "Bridge listens on loopback only. Page inspection starts after an explicit command.",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        location.unlink(missing_ok=True)
        # The extension can remain loaded, but its token no longer reaches a service.
        credentials.unlink(missing_ok=True)


class Client:
    def __init__(self, manifest: Path):
        location = json.loads(locator(manifest).read_text())
        path = Path(location["credentials_file"])
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise PermissionError("Browser bridge credentials must be private")
        credentials = json.loads(path.read_text())
        parsed = urlsplit(credentials["url"])
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or not parsed.port
            or parsed.path
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Bridge endpoint must be a local loopback service")
        self.url, self.token = credentials["url"], credentials["token"]
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, endpoint: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.url + endpoint,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(json.load(exc).get("error", "Bridge request failed")) from exc
        if result.get("error"):
            raise RuntimeError(result["error"])
        return result
