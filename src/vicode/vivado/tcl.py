"""Tcl generation helpers. All dynamic values pass through :func:`quote` (design Section 7.2)."""

from __future__ import annotations

import re

_SAFE = re.compile(r"[A-Za-z0-9_./:@%+=,-]")


def quote(value: str) -> str:
    """Return a single Tcl word that evaluates to exactly ``value``.

    Every character outside a conservative safe set is backslash-escaped, so substitutions
    (``$``, ``[``), word separators (space, ``;``, newline), braces and quotes cannot change
    the meaning of the generated script.
    """
    if value == "":
        return '""'
    out: list[str] = []
    for ch in value:
        if _SAFE.fullmatch(ch):
            out.append(ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append(f"\\x{ord(ch):02x}")
        elif ord(ch) > 126:
            code = ord(ch)
            out.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            out.append("\\" + ch)
    return "".join(out)


def path(value: str) -> str:
    """Quote a filesystem path for Tcl, using forward slashes (valid on Windows too)."""
    return quote(value.replace("\\", "/"))


PROBE_BEGIN = "VICODE:begin"
PROBE_END = "VICODE:end"


def probe_script(part: str | None = None) -> str:
    """Tcl run by ``vicode doctor`` to prove that Vivado executes batch Tcl.

    The script prints marker lines that the doctor requires: an exit status of 0 alone is
    never accepted as proof that Vivado worked.
    """
    lines = [
        f'puts "{PROBE_BEGIN}"',
        'puts "VICODE:version=[version -short]"',
    ]
    if part:
        lines.append(f'puts "VICODE:part_found=[llength [get_parts -quiet {quote(part)}]]"')
    lines.append(f'puts "{PROBE_END}"')
    return "\n".join(lines) + "\n"


def parse_probe_output(lines: list[str]) -> dict[str, str] | None:
    """Extract ``VICODE:key=value`` markers; None unless both begin and end markers appear."""
    values: dict[str, str] = {}
    begun = ended = False
    for raw in lines:
        line = raw.strip()
        if line == PROBE_BEGIN:
            begun = True
        elif line == PROBE_END:
            ended = True
        elif line.startswith("VICODE:") and "=" in line:
            key, _, val = line[len("VICODE:"):].partition("=")
            values[key] = val
    return values if begun and ended else None
