"""Structured results shared by every operation (Section 6.1 of the design)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from vicode import PROTOCOL_VERSION, __version__


class ExitCode(enum.IntEnum):
    """Process exit codes of the ``vicode`` command (documented in docs/cli.md)."""

    OK = 0
    FAILED = 1  # the operation ran and failed
    USAGE_OR_CONFIG = 2  # invalid usage or invalid configuration
    ENVIRONMENT = 3  # environment problem (Vivado missing, unusable, ...)
    CANCELLED = 4
    NOT_AVAILABLE = 5  # command exists but is not available in this release


SEVERITIES = ("info", "warning", "critical_warning", "error")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Diagnostic:
    severity: str
    message: str
    id: str | None = None
    category: str | None = None
    file: str | None = None
    line: int | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"severity": self.severity, "message": self.message}
        for key in ("id", "category", "file", "line", "hint"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass
class OperationResult:
    operation: str
    status: str = "failed"  # succeeded | failed | cancelled
    tool: str | None = "vivado"
    tool_version: str | None = None
    target_part: str | None = None
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    exit_code: int | None = None  # exit status of the external tool, if one ran
    vicode_exit_code: int = int(ExitCode.FAILED)
    logs: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def finish(self, exit_code: ExitCode, summary: str) -> "OperationResult":
        self.vicode_exit_code = int(exit_code)
        self.status = {
            ExitCode.OK: "succeeded",
            ExitCode.CANCELLED: "cancelled",
        }.get(exit_code, "failed")
        self.summary = summary
        self.finished_at = utc_now()
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL_VERSION,
            "vicode_version": __version__,
            "operation": self.operation,
            "status": self.status,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "target_part": self.target_part,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "vicode_exit_code": self.vicode_exit_code,
            "logs": list(self.logs),
            "reports": list(self.reports),
            "artifacts": list(self.artifacts),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "summary": self.summary,
            "details": self.details,
        }
