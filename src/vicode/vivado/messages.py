"""Parse Vivado log messages by their stable identifiers (design Section 11.4)."""

from __future__ import annotations

import re

from vicode.results import Diagnostic

_ID = re.compile(
    r"^(?P<sev>INFO|WARNING|CRITICAL WARNING|ERROR):\s+"
    r"\[(?P<cat>[A-Za-z][A-Za-z0-9]*)\s+(?P<num>[A-Za-z0-9]+-\d+)\]\s*"
    r"(?P<text>.*?)"
    r"(?:\s+\[(?P<file>[^\[\]]+?):(?P<line>\d+)\])?\s*$"
)
_BARE = re.compile(r"^(?P<sev>CRITICAL WARNING|WARNING|ERROR):\s+(?P<text>\S.*?)\s*$")
_SEVERITY = {
    "INFO": "info",
    "WARNING": "warning",
    "CRITICAL WARNING": "critical_warning",
    "ERROR": "error",
}


def parse_line(line: str) -> Diagnostic | None:
    text = line.rstrip("\r\n")
    match = _ID.match(text)
    if match:
        file = match.group("file")
        return Diagnostic(
            severity=_SEVERITY[match.group("sev")],
            message=match.group("text"),
            id=f"{match.group('cat')} {match.group('num')}",
            file=file.replace("\\", "/") if file else None,
            line=int(match.group("line")) if match.group("line") else None,
        )
    bare = _BARE.match(text)
    if bare:
        return Diagnostic(severity=_SEVERITY[bare.group("sev")], message=bare.group("text"))
    return None


def parse_lines(lines: list[str], include_info: bool = False, limit: int = 50) -> list[Diagnostic]:
    """Parse and de-duplicate messages. INFO messages are dropped unless requested."""
    out: list[Diagnostic] = []
    seen: set[tuple] = set()
    for line in lines:
        diag = parse_line(line)
        if diag is None or (diag.severity == "info" and not include_info):
            continue
        key = (diag.severity, diag.id, diag.message, diag.file, diag.line)
        if key in seen:
            continue
        seen.add(key)
        out.append(diag)
        if len(out) >= limit:
            break
    return out
