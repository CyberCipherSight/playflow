from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class StateStore:
    """Private, atomic stage journal. One writer per project is supported."""

    project_dir: Path
    directory: Path | None = None

    @property
    def path(self) -> Path:
        directory = self.directory if self.directory is not None else self.project_dir / ".playflow"
        return directory / "state.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "steps": {}}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid state JSON: {self.path}; restore or remove it") from exc
        if (
            not isinstance(state, dict)
            or state.get("schema_version") != 1
            or not isinstance(state.get("steps"), dict)
        ):
            raise ValueError(f"Unsupported state format: {self.path}")
        return state

    def save(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, indent=2, sort_keys=True)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def mark(self, step: str, status: str, **details: Any) -> None:
        state = self.load()
        state["steps"][step] = {
            **details,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save(state)

    @contextmanager
    def stage(self, step: str) -> Iterator[dict[str, Any]]:
        details: dict[str, Any] = {}
        self.mark(step, "running")
        try:
            yield details
        except BaseException as exc:
            # Exception messages and subprocess logs may contain credentials.
            self.mark(step, "failed", error_type=type(exc).__name__)
            raise
        else:
            self.mark(step, "done", **details)
