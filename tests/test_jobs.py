import json
import os
import shutil
import subprocess
import sys

import unittest

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
        self.assertEqual(jobs.git_state(self.tmp), {"revision": None, "dirty": None})
        run = lambda *a: subprocess.run(["git", "-C", str(self.tmp), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        check=True, capture_output=True)
        run("init", "-q")
        (self.tmp / "f.txt").write_text("1")
        run("add", "f.txt")
        run("commit", "-q", "-m", "init")
        state = jobs.git_state(self.tmp)
        self.assertEqual(len(state["revision"]), 40)
        self.assertFalse(state["dirty"])
        (self.tmp / "f.txt").write_text("2")
        self.assertTrue(jobs.git_state(self.tmp)["dirty"])
