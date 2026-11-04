import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from vicode import jobs
from vicode.results import ExitCode, OperationResult
from tests.support import TempDirTestCase


class LockTests(TempDirTestCase):
    def test_acquire_and_release(self):
        build = self.tmp / "build"
        lock = jobs.ProjectLock(build, "synth")
        lock.acquire()
        info = json.loads((build / jobs.LOCK_NAME).read_text())
        self.assertEqual((info["pid"], info["operation"]), (os.getpid(), "synth"))
        lock.release()
        self.assertFalse((build / jobs.LOCK_NAME).exists())
        lock.release()  # releasing twice is harmless

    def test_second_job_is_refused_while_first_is_alive(self):
        build = self.tmp / "build"
        with jobs.ProjectLock(build, "synth"):
            with self.assertRaises(jobs.ProjectBusy) as ctx:
                jobs.ProjectLock(build, "impl").acquire()
            self.assertEqual(ctx.exception.pid, os.getpid())
            self.assertEqual(ctx.exception.operation, "synth")
        jobs.ProjectLock(build, "impl").acquire()  # free again

    def test_stale_lock_is_reclaimed(self):
        build = self.tmp / "build"
        build.mkdir()
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        (build / jobs.LOCK_NAME).write_text(json.dumps({"pid": dead.pid, "operation": "old"}))
        with jobs.ProjectLock(build, "new"):
            self.assertEqual(json.loads((build / jobs.LOCK_NAME).read_text())["operation"], "new")

    def test_corrupt_lock_is_treated_as_stale(self):
        build = self.tmp / "build"
        build.mkdir()
        (build / jobs.LOCK_NAME).write_text("not json")
        with jobs.ProjectLock(build, "x"):
            pass

    def test_released_on_exception(self):
        build = self.tmp / "build"
        with self.assertRaises(RuntimeError):
            with jobs.ProjectLock(build, "x"):
                raise RuntimeError("boom")
        self.assertFalse((build / jobs.LOCK_NAME).exists())

    def test_pid_alive(self):
        self.assertTrue(jobs.pid_alive(os.getpid()))
        self.assertFalse(jobs.pid_alive(0))
        self.assertFalse(jobs.pid_alive(-5))
        done = subprocess.Popen([sys.executable, "-c", "pass"])
        done.wait()
        self.assertFalse(jobs.pid_alive(done.pid))


class RecordTests(TempDirTestCase):
    def test_layout_and_result_record(self):
        layout = jobs.build_layout(self.tmp).ensure()
        for d in (layout.vivado, layout.logs, layout.reports, layout.artifacts, layout.metadata):
            self.assertTrue(d.is_dir())
        result = OperationResult("doctor").finish(ExitCode.OK, "fine")
        path = jobs.write_result(layout, result)
        self.assertEqual(path, layout.metadata / "doctor-result.json")
        data = json.loads(path.read_text())
        self.assertEqual((data["operation"], data["status"], data["vicode_exit_code"], data["protocol"]),
                         ("doctor", "succeeded", 0, 1))
        self.assertFalse(list(layout.metadata.glob("*.tmp")))
        jobs.write_result(layout, result)  # overwrite works

    def test_result_dict_has_the_documented_fields(self):
        data = OperationResult("synthesis").finish(ExitCode.FAILED, "x").to_dict()
        for key in ("operation", "status", "tool", "tool_version", "target_part", "started_at", "finished_at",
                    "exit_code", "logs", "reports", "artifacts", "diagnostics", "summary", "protocol", "vicode_version"):
            self.assertIn(key, data)
        json.dumps(data)  # must be serialisable
        self.assertEqual(OperationResult("x").finish(ExitCode.CANCELLED, "").status, "cancelled")
        self.assertEqual(OperationResult("x").finish(ExitCode.ENVIRONMENT, "").status, "failed")

    def test_config_hash(self):
        a = jobs.config_hash({"a": 1, "b": [1, 2]})
        self.assertEqual(a, jobs.config_hash({"b": [1, 2], "a": 1}))
        self.assertNotEqual(a, jobs.config_hash({"a": 2, "b": [1, 2]}))
        self.assertEqual(len(a), 64)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_state(self):
        self.assertEqual(jobs.git_state(self.tmp, trusted=False), {"revision": None, "dirty": None})
        self.assertEqual(jobs.git_state(self.tmp, trusted=True), {"revision": None, "dirty": None})
        run = lambda *a: subprocess.run(["git", "-C", str(self.tmp), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        check=True, capture_output=True)
        run("init", "-q")
        (self.tmp / "f.txt").write_text("1")
        run("add", "f.txt")
        run("commit", "-q", "-m", "init")

        # Untrusted project returns None without running git
        untrusted_state = jobs.git_state(self.tmp, trusted=False)
        self.assertEqual(untrusted_state, {"revision": None, "dirty": None})

        # Trusted project returns revision and dirty flag
        state = jobs.git_state(self.tmp, trusted=True)
        self.assertEqual(len(state["revision"]), 40)
        self.assertFalse(state["dirty"])
        (self.tmp / "f.txt").write_text("2")
        self.assertTrue(jobs.git_state(self.tmp, trusted=True)["dirty"])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_state_ignores_core_fsmonitor_hook(self):
        run = lambda *a: subprocess.run(["git", "-C", str(self.tmp), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        check=True, capture_output=True)
        run("init", "-q")
        (self.tmp / "f.txt").write_text("1")
        run("add", "f.txt")
        run("commit", "-q", "-m", "init")

        marker = self.tmp / "pwned.txt"
        if sys.platform == "win32":
            script = self.tmp / "fsmonitor.bat"
            script.write_text(f'@echo off\r\necho pwned > "{marker}"\r\n', encoding="utf-8")
        else:
            script = self.tmp / "fsmonitor.sh"
            script.write_text(f'#!/bin/sh\necho pwned > "{marker}"\n', encoding="utf-8")
            script.chmod(0o755)

        run("config", "core.fsmonitor", str(script))
        # Even with trusted=True, CLI overrides prevent core.fsmonitor execution
        state = jobs.git_state(self.tmp, trusted=True)
        self.assertEqual(len(state["revision"]), 40)
        self.assertFalse(marker.exists(), "core.fsmonitor hook script must not have been executed")

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_state_clean_filter_execution_prevented(self):
        run = lambda *a: subprocess.run(["git", "-C", str(self.tmp), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        check=True, capture_output=True)
        run("init", "-q")
        marker = self.tmp / "clean_filter_marker.txt"

        if sys.platform == "win32":
            payload = self.tmp / "payload.bat"
            payload.write_text(f'@echo off\r\necho pwned > "{marker}"\r\nfindstr .', encoding="utf-8")
        else:
            payload = self.tmp / "payload.sh"
            payload.write_text(f'#!/bin/sh\necho pwned > "{marker}"\ncat', encoding="utf-8")
            payload.chmod(0o755)

        (self.tmp / ".gitattributes").write_text("*.txt filter=evil\n", encoding="utf-8")
        run("add", ".gitattributes")
        run("config", "filter.evil.clean", str(payload).replace("\\", "/"))

        (self.tmp / "f.txt").write_text("content 1\n", encoding="utf-8")
        run("add", "f.txt")
        run("commit", "-m", "init")

        if marker.exists():
            marker.unlink()

        # Modify f.txt with same length content so Git must invoke clean filter
        (self.tmp / "f.txt").write_text("content 2\n", encoding="utf-8")

        # 1. POSITIVE CONTROL: Unprotected git status executes clean filter
        subprocess.run(["git", "-C", str(self.tmp), "status", "--porcelain"], capture_output=True, text=True)
        self.assertTrue(marker.exists(), "Positive control failed: clean filter was not triggered by git status")
        marker.unlink()

        # 2. UNTRUSTED CALL: git_state(trusted=False) never invokes Git, preventing execution
        untrusted_state = jobs.git_state(self.tmp, trusted=False)
        self.assertEqual(untrusted_state, {"revision": None, "dirty": None})
        self.assertFalse(marker.exists(), "Untrusted project must never invoke git or trigger clean filter")

        # 3. TRUSTED CALL: git_state(trusted=True) queries git and retrieves metadata
        trusted_state = jobs.git_state(self.tmp, trusted=True)
        self.assertIsNotNone(trusted_state["revision"])
        self.assertTrue(trusted_state["dirty"])

    def test_safe_git_command_rejects_planted_and_accepts_trusted(self):
        from unittest.mock import patch

        # 1. Test planted git in repository directory is rejected when returned by which()
        for ext in (".exe", ".bat") if sys.platform == "win32" else ("",):
            planted_repo = self.tmp / "repo" / f"git{ext}"
            planted_repo.parent.mkdir(parents=True, exist_ok=True)
            planted_repo.write_text("fake", encoding="utf-8")

            with patch("vicode.jobs.shutil.which", return_value=str(planted_repo)):
                with patch.dict(os.environ, {"ProgramFiles": str(self.tmp / "none"),
                                             "ProgramFiles(x86)": str(self.tmp / "none")}):
                    res = jobs._safe_git_command(self.tmp / "repo")
                    self.assertIsNone(res, f"Planted repo git {ext} must be rejected, yielding None")

        # 2. Test planted git in current directory is rejected when returned by which()
        for ext in (".bat", ".exe") if sys.platform == "win32" else ("",):
            planted_cwd = self.tmp / "cwd" / f"git{ext}"
            planted_cwd.parent.mkdir(parents=True, exist_ok=True)
            planted_cwd.write_text("fake", encoding="utf-8")

            old_cwd = os.getcwd()
            try:
                os.chdir(self.tmp / "cwd")
                with patch("vicode.jobs.shutil.which", return_value=str(planted_cwd)):
                    with patch.dict(os.environ, {"ProgramFiles": str(self.tmp / "none"),
                                                 "ProgramFiles(x86)": str(self.tmp / "none")}):
                        res = jobs._safe_git_command(self.tmp / "other_repo")
                        self.assertIsNone(res, f"Planted cwd git {ext} must be rejected, yielding None")
            finally:
                os.chdir(old_cwd)

        # 3. Test legitimate external git is accepted when returned by which()
        trusted = self.tmp / "trusted_bin" / ("git.exe" if sys.platform == "win32" else "git")
        trusted.parent.mkdir(parents=True, exist_ok=True)
        trusted.write_text("real", encoding="utf-8")

        with patch("vicode.jobs.shutil.which", return_value=str(trusted)):
            res = jobs._safe_git_command(self.tmp / "repo")
            self.assertEqual(Path(os.path.realpath(res)), Path(os.path.realpath(str(trusted))))

    def test_git_state_defaults_to_untrusted_without_spawning_git(self):
        from unittest.mock import patch
        with patch("subprocess.run") as mock_run:
            state = jobs.git_state(self.tmp)
            self.assertEqual(state, {"revision": None, "dirty": None})
            mock_run.assert_not_called()

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_state_overrides_core_hooks_path(self):
        from unittest.mock import patch
        run = lambda *a: subprocess.run(["git", "-C", str(self.tmp), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *a],
                                        check=True, capture_output=True)
        run("init", "-q")
        (self.tmp / "f.txt").write_text("content\n", encoding="utf-8")
        run("add", "f.txt")
        run("commit", "-q", "-m", "init")

        calls = []
        orig_run = subprocess.run
        def record_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and len(cmd) > 0 and "git" in str(cmd[0]).lower():
                calls.append(cmd)
            return orig_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=record_run):
            state = jobs.git_state(self.tmp, trusted=True)

        self.assertIsNotNone(state["revision"])
        self.assertTrue(len(calls) >= 1)
        for cmd in calls:
            self.assertIn("-c", cmd)
            idx = cmd.index("core.hooksPath=") if "core.hooksPath=" in cmd else -1
            self.assertTrue(idx > 0 and cmd[idx - 1] == "-c", "core.hooksPath= must be passed with -c")
