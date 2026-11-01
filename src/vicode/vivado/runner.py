"""Run generated Tcl through Vivado in batch mode with explicit log, journal and temp options."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from vicode.jobs import Layout
from vicode.vivado.process import RunOutcome, build_env, run_process

MAX_CAPTURED_LINES = 200_000


@dataclass
class TclRun:
    outcome: RunOutcome
    script: Path
    log: Path  # raw captured stdout + stderr
    vivado_log: Path  # Vivado's own -log file
    lines: list[str] = field(default_factory=list)


def run_tcl(
    launcher: str,
    script_text: str,
    layout: Layout,
    name: str,
    env: Mapping[str, str],
    *,
    timeout: float | None = None,
    cancel: threading.Event | None = None,
    on_line: Callable[[str, str], None] | None = None,
) -> TclRun:
    layout.ensure()
    script = layout.vivado / f"{name}.tcl"
    script.write_text(script_text, encoding="utf-8", newline="\n")
    log = layout.logs / f"{name}.log"
    log.write_text("", encoding="utf-8")  # fresh raw log per run
    vivado_log = layout.vivado / f"{name}.vivado.log"
    journal = layout.vivado / f"{name}.jou"
    temp_dir = layout.vivado / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # The working directory is layout.vivado, so every file argument is a short relative name.
    # That keeps paths with spaces and special characters out of the (batch-file) command line;
    # only the launcher path itself is ever quoted.
    args = [
        launcher, "-mode", "batch", "-source", script.name,
        "-log", vivado_log.name, "-journal", journal.name, "-tempDir", temp_dir.name, "-notrace",
    ]
    captured: list[str] = []

    def collect(stream: str, line: str) -> None:
        if len(captured) < MAX_CAPTURED_LINES:
            captured.append(line)
        if on_line:
            on_line(stream, line)

    outcome = run_process(args, cwd=layout.vivado, env=build_env(env), timeout=timeout, cancel=cancel,
                          on_line=collect, log_path=log)
    return TclRun(outcome, script, log, vivado_log, captured)
