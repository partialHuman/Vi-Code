"""Build layout, project lock and build records (design Sections 11.1, 11.2 and NFR-03)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vicode.results import OperationResult, utc_now

LOCK_NAME = ".vicode.lock"


@dataclass(frozen=True)
class Layout:
    root: Path
    build: Path
    vivado: Path
    logs: Path
    reports: Path
    artifacts: Path
    metadata: Path

    def ensure(self) -> "Layout":
        for p in (self.build, self.vivado, self.logs, self.reports, self.artifacts, self.metadata):
            p.mkdir(parents=True, exist_ok=True)
        return self


def build_layout(root: Path) -> Layout:
    root = Path(root)
    build = root / "build"
    return Layout(root, build, build / "vivado", build / "logs", build / "reports",
                  build / "artifacts", build / "metadata")


def pid_alive(pid: int) -> bool:
    """True if a process with this id exists (zombies count as dead)."""
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - exercised on Windows only
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: the process exists
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            state = fh.read().rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except (OSError, IndexError):
        return True


class ProjectBusy(RuntimeError):
    def __init__(self, pid: int | None, operation: str | None, path: Path) -> None:
        self.pid, self.operation, self.path = pid, operation, path
        who = f"process {pid}" if pid else "another process"
        what = f" running '{operation}'" if operation else ""
        super().__init__(f"project is busy: {who}{what} holds {path}")


class ProjectLock:
    """One mutating job per project at a time. Stale locks (dead pid) are reclaimed."""

    def __init__(self, build_dir: Path, operation: str) -> None:
        self.path = Path(build_dir) / LOCK_NAME
        self.operation = operation
        self._held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"pid": os.getpid(), "operation": self.operation, "started_at": utc_now()})
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pid, op = self._read_holder()
                if pid and pid_alive(pid):
                    raise ProjectBusy(pid, op, self.path) from None
                try:  # stale: holder is gone
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            self._held = True
            return
        raise ProjectBusy(None, None, self.path)

    def _read_holder(self) -> tuple[int | None, str | None]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return int(data.get("pid")), data.get("operation")
        except (OSError, ValueError, TypeError):
            return None, None

    def release(self) -> None:
        if self._held:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._held = False

    def __enter__(self) -> "ProjectLock":
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


def config_hash(resolved: dict[str, Any]) -> str:
    blob = json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _safe_git_command(repo_path: Path) -> str | None:
    git_bin = shutil.which("git")
    if git_bin:
        try:
            git_real = Path(os.path.realpath(git_bin)).resolve()
            cwd_real = Path(os.path.realpath(os.getcwd())).resolve()
            repo_real = Path(os.path.realpath(str(repo_path))).resolve()
            if (
                git_real == cwd_real
                or git_real.parent == cwd_real
                or git_real == repo_real
                or repo_real in git_real.parents
            ):
                git_bin = None
        except OSError:
            git_bin = None
    if not git_bin and sys.platform == "win32":
        for prefix in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                       os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            candidate = Path(prefix) / "Git" / "cmd" / "git.exe"
            if candidate.is_file():
                git_bin = str(candidate)
                break
    return git_bin


def git_state(path: Path, trusted: bool = False) -> dict[str, Any]:
    """Source revision and uncommitted-changes flag for trusted projects; never raises."""
    if not trusted:
        return {"revision": None, "dirty": None}

    git_bin = _safe_git_command(path)
    if not git_bin:
        return {"revision": None, "dirty": None}

    git_env = dict(os.environ)
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_TERMINAL_PROMPT"] = "0"

    def git(*args: str) -> str | None:
        try:
            cmd = [
                git_bin,
                "-c", "core.fsmonitor=false",
                "-c", "core.useBuiltinFSMonitor=false",
                "-c", "core.hooksPath=",
                "--no-optional-locks",
                "-C", str(path),
                *args,
            ]
            done = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=git_env,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    revision = git("rev-parse", "HEAD")
    if revision is None:
        return {"revision": None, "dirty": None}
    status = git("status", "--porcelain")
    return {"revision": revision, "dirty": bool(status) if status is not None else None}


def result_path(layout: Layout, operation: str) -> Path:
    return layout.metadata / f"{operation}-result.json"


def write_result(layout: Layout, result: OperationResult) -> Path:
    """Persist the structured result (atomic replace)."""
    layout.metadata.mkdir(parents=True, exist_ok=True)
    target = result_path(layout, result.operation)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target
