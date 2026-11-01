"""Structured job events (Section 5.4): the same stream feeds the CLI, CI and the future extension."""

from __future__ import annotations

import json
import uuid
from typing import Any, TextIO

from vicode import PROTOCOL_VERSION
from vicode.results import Diagnostic, utc_now


class EventSink:
    """Collects job events and, optionally, writes them as JSON lines to a stream."""

    def __init__(self, stream: TextIO | None = None, job_id: str | None = None) -> None:
        self.stream = stream
        self.job_id = job_id or uuid.uuid4().hex[:12]
        self.events: list[dict[str, Any]] = []

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {
            "protocol": PROTOCOL_VERSION,
            "event": event,
            "job_id": self.job_id,
            "ts": utc_now(),
            **fields,
        }
        self.events.append(record)
        if self.stream is not None:
            self.stream.write(json.dumps(record, ensure_ascii=True) + "\n")
            self.stream.flush()
        return record

    def started(self, operation: str) -> None:
        self.emit("job.started", operation=operation)

    def stage(self, stage: str) -> None:
        self.emit("job.stage", stage=stage)

    def message(self, diagnostic: Diagnostic) -> None:
        self.emit("job.message", **diagnostic.to_dict())

    def finished(self, status: str, exit_code: int, result: dict[str, Any] | None = None,
                 result_path: str | None = None) -> None:
        fields: dict[str, Any] = {"status": status, "vicode_exit_code": exit_code}
        if result_path:
            fields["result_path"] = result_path
        if result is not None:
            fields["result"] = result
        self.emit("job.finished", **fields)
