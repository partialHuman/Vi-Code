import os
import subprocess
import sys
import threading
import time
import unittest.mock
from pathlib import Path

from vicode.jobs import pid_alive
from vicode.vivado import process
from tests.support import TempDirTestCase

PY = sys.executable


def wait_for(predicate, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class RunProcessTests(TempDirTestCase):
    def run_py(self, code: str, **kw):
        env = process.build_env(os.environ)
        return process.run_process([PY, "-c", code], self.tmp, env, **kw)

    def test_captures_output_and_exit_code(self):
        log = self.tmp / "run.log"
        lines = []
        out = self.run_py("import sys; print('hello'); print('oops', file=sys.stderr); sys.exit(3)",
                          log_path=log, on_line=lambda s, l: lines.append((s, l)))
        self.assertEqual(out.exit_code, 3)
        self.assertFalse(out.timed_out or out.cancelled)
        self.assertIn(("stdout", "hello"), lines)
        self.assertIn(("stderr", "oops"), lines)
        text = log.read_text(encoding="utf-8")
        self.assertIn("hello", text)
        self.assertIn("oops", text)

    def test_success(self):
        self.assertEqual(self.run_py("pass").exit_code, 0)

    def test_timeout_stops_the_process(self):
        t0 = time.monotonic()
        out = self.run_py("import time; time.sleep(60)", timeout=0.6)
        self.assertTrue(out.timed_out)
        self.assertLess(time.monotonic() - t0, 20)
        self.assertNotEqual(out.exit_code, 0)

    def test_cancel_event(self):
        cancel = threading.Event()
        threading.Timer(0.5, cancel.set).start()
        out = self.run_py("import time; time.sleep(60)", cancel=cancel)
        self.assertTrue(out.cancelled)
        self.assertFalse(out.timed_out)

    def test_cancel_terminates_the_whole_process_tree(self):
        pidfile = self.tmp / "child.pid"
        parent = (
            "import subprocess, sys, time\n"
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            f"open({str(pidfile)!r}, 'w').write(str(c.pid))\n"
            "time.sleep(120)\n"
        )
        cancel = threading.Event()

        def trigger():
            wait_for(pidfile.exists)
            time.sleep(0.2)
            cancel.set()

        threading.Thread(target=trigger, daemon=True).start()
        out = self.run_py(parent, cancel=cancel)
        self.assertTrue(out.cancelled)
        child_pid = int(pidfile.read_text())
        self.assertTrue(wait_for(lambda: not pid_alive(child_pid), 10), "grandchild survived cancellation")

    def test_start_failure_is_reported_not_raised(self):
        out = process.run_process([str(self.tmp / "no-such-program")], self.tmp, {})
        self.assertIsNone(out.exit_code)
        self.assertIn("could not start", out.error)

    @unittest.skipUnless(process.IS_WINDOWS, "Windows-specific taskkill resolution test")
    def test_terminate_tree_invokes_absolute_system32_taskkill_and_never_bare_taskkill(self):
        proc = unittest.mock.MagicMock()
        proc.pid = 4321
        with unittest.mock.patch("subprocess.run") as mock_run:
            process.terminate_tree(proc)
            self.assertTrue(mock_run.called, "subprocess.run must be called for taskkill")
            cmd = mock_run.call_args[0][0]
            self.assertTrue(
                cmd[0].lower().endswith(r"\system32\taskkill.exe"),
                f"Expected absolute System32 taskkill.exe path, got {cmd[0]!r}",
            )
            self.assertNotEqual(cmd[0].lower(), "taskkill")
            self.assertNotEqual(cmd[0].lower(), "taskkill.exe")
            self.assertEqual(cmd[1:], ["/PID", "4321", "/T", "/F"])
            proc.kill.assert_called_once()

    @unittest.skipUnless(process.IS_WINDOWS, "Windows-specific taskkill resolution test")
    def test_terminate_tree_safe_fallback_when_taskkill_missing(self):
        proc = unittest.mock.MagicMock()
        proc.pid = 4321
        with unittest.mock.patch("os.path.isfile", return_value=False):
            with unittest.mock.patch("subprocess.run") as mock_run:
                process.terminate_tree(proc)
                mock_run.assert_not_called()
                proc.kill.assert_called_once()


class EnvironmentTests(TempDirTestCase):
    def test_allowlist(self):
        base = {"PATH": "/bin", "MY_SECRET_TOKEN": "s3cret", "XILINXD_LICENSE_FILE": "2100@lic", "LM_LICENSE_FILE": "x",
                "XILINX_VIVADO": "/v", "AWS_SECRET_ACCESS_KEY": "k", "HOME": "/h", "other_vivado": "no"}
        env = process.build_env(base)
        self.assertEqual(set(env), {"PATH", "XILINXD_LICENSE_FILE", "LM_LICENSE_FILE", "XILINX_VIVADO", "HOME"})

    def test_extra_variables(self):
        self.assertEqual(process.build_env({}, {"A": "1"}), {"A": "1"})

    def test_child_does_not_see_unlisted_variables(self):
        base = dict(os.environ, MY_SECRET_TOKEN="s3cret")
        out_file = self.tmp / "env.txt"
        code = f"import os; open({str(out_file)!r}, 'w').write(','.join(sorted(os.environ)))"
        process.run_process([PY, "-c", code], self.tmp, process.build_env(base))
        seen = out_file.read_text().split(",")
        self.assertNotIn("MY_SECRET_TOKEN", seen)


class BatchArgumentTests(TempDirTestCase):
    def test_safe_arguments_pass(self):
        process.validate_batch_args([
            r"C:\Program Files (x86)\Xilinx\Vivado\2023.2\bin\vivado.bat", "-mode", "batch",
            r"C:\Users\Jane Doe\proj\build\vivado\environment.tcl", "-notrace"])

    def test_dangerous_arguments_are_rejected(self):
        for bad in ("a&calc", "a|b", "a>b", "a<b", "a^b", "%PATH%", "a!b", 'a"b', "a`b", "a,b", "a;b", "a=b",
                    "line\nbreak", "cr\rx", "nul\x00"):
            with self.assertRaises(process.UnsafeArgument, msg=repr(bad)):
                process.validate_batch_args(["ok", bad])

    def test_batch_launcher_rejected_before_start(self):
        with self.assertRaises(process.UnsafeArgument):
            process.run_process([str(self.tmp / "vivado.bat"), "-source", "a&b.tcl"], self.tmp, {})

    def test_non_batch_launchers_are_not_restricted(self):
        self.assertFalse(process.needs_batch_validation("/opt/vivado"))
        self.assertTrue(process.needs_batch_validation("C:\\x\\VIVADO.BAT"))
        self.assertTrue(process.needs_batch_validation("x.cmd"))
