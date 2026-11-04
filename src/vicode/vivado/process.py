"""Safe subprocess execution with log capture, timeout and cancellation (design Section 8.3).

* Arguments are always a list, never a composed command string.
* ``.bat`` / ``.cmd`` launchers go through the Windows command interpreter, so their
  arguments are checked against an allowlist before launch.
* Only a fixed set of environment variables is passed on (licence variables included, never logged).
* Cancellation and timeouts terminate the whole process tree.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from vicode.results import utc_now

IS_WINDOWS = sys.platform == "win32"

UNSAFE_BATCH_CHARS = frozenset('&|<>^%!"`,;=\r\n\x00')

ENV_ALLOW = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "USERNAME", "USER", "LOGNAME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "COMPUTERNAME", "LANG", "LC_ALL", "SHELL", "XILINXD_LICENSE_FILE",
    "LM_LICENSE_FILE",
})
ENV_ALLOW_PREFIXES = ("XILINX", "VIVADO", "RDI_")


class UnsafeArgument(ValueError):
    """An argument for a batch-file launcher contains characters cmd.exe could misinterpret."""


def needs_batch_validation(executable: str) -> bool:
    return executable.lower().endswith((".bat", ".cmd"))


def validate_batch_args(args: Sequence[str]) -> None:
    for arg in args:
        bad = sorted({c for c in arg if c in UNSAFE_BATCH_CHARS})
        if bad:
            shown = "".join(c if c.isprintable() else repr(c)[1:-1] for c in bad)
            raise UnsafeArgument(
                f"argument {arg!r} contains characters that are unsafe for a batch launcher ({shown}); "
                "rename the path or move the project to a simpler location"
            )


def build_env(base: Mapping[str, str], extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the child environment from an allowlist."""
    env: dict[str, str] = {}
    for key, value in base.items():
        upper = key.upper()
        if upper in ENV_ALLOW or upper.startswith(ENV_ALLOW_PREFIXES):
            env[key] = value
    if extra:
        env.update(extra)
    return env


@dataclass
class RunOutcome:
    exit_code: int | None
    started_at: str
    finished_at: str
    duration_s: float
    timed_out: bool = False
    cancelled: bool = False
    error: str | None = None  # the process could not be started


def terminate_tree(proc: subprocess.Popen, grace: float = 3.0) -> None:
    """Terminate ``proc`` and everything it started."""
    if IS_WINDOWS:
        system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
        taskkill_bin = os.path.join(system_root, "System32", "taskkill.exe")
        if os.path.isfile(taskkill_bin):
            try:
                subprocess.run([taskkill_bin, "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # also reaps stragglers left in the group
    except (ProcessLookupError, PermissionError):
        pass


def run_process(
    args: Sequence[str],
    cwd: Path | str,
    env: Mapping[str, str],
    *,
    timeout: float | None = None,
    cancel: threading.Event | None = None,
    on_line: Callable[[str, str], None] | None = None,
    log_path: Path | str | None = None,
    poll: float = 0.05,
) -> RunOutcome:
    """Run ``args`` to completion, capturing stdout and stderr line by line."""
    started = utc_now()
    t0 = time.monotonic()
    args = [str(a) for a in args]
    if needs_batch_validation(args[0]):
        validate_batch_args(args)

    kwargs: dict = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            args, cwd=str(cwd), env=dict(env), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs,
        )
    except OSError as exc:
        return RunOutcome(None, started, utc_now(), time.monotonic() - t0, error=f"could not start {args[0]}: {exc}")

    log_file = open(log_path, "a", encoding="utf-8", errors="replace") if log_path else None
    write_lock = threading.Lock()

    def pump(stream, name: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                with write_lock:
                    if log_file:
                        log_file.write(line if line.endswith("\n") else line + "\n")
                        log_file.flush()
                if on_line:
                    on_line(name, line.rstrip("\r\n"))
        except (OSError, ValueError):
            pass

    readers = [
        threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True),
    ]
    for t in readers:
        t.start()

    timed_out = cancelled = False
    try:
        try:
            while True:
                try:
                    proc.wait(timeout=poll)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    terminate_tree(proc)
                    break
                if timeout is not None and time.monotonic() - t0 > timeout:
                    timed_out = True
                    terminate_tree(proc)
                    break
        except KeyboardInterrupt:  # Ctrl+C: stop the whole tree and report a cancelled run
            cancelled = True
            terminate_tree(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            terminate_tree(proc, grace=0)
        for t in readers:
            t.join(timeout=5)
    finally:
        if log_file:
            log_file.close()
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
    return RunOutcome(proc.returncode, started, utc_now(), time.monotonic() - t0,
                      timed_out=timed_out, cancelled=cancelled)
