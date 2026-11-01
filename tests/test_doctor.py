"""Contract tests: ``vicode doctor`` against the fake Vivado (design Section 12.4)."""
import json
import os
import threading
import time
from pathlib import Path

from vicode import config, doctor, jobs
from vicode.events import EventSink
from vicode.results import ExitCode
from tests.support import TempDirTestCase, VALID_MANIFEST, make_fake_vivado


class DoctorTestCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.tools = self.tmp / "tools"
        self.marker = self.tmp / "marker"
        self.project = self.tmp / "proj"
        self.project.mkdir()

    def install(self, **kw) -> Path:
        kw.setdefault("marker_dir", self.marker)
        return make_fake_vivado(self.tools, **kw)

    def write_project(self, text=VALID_MANIFEST):
        (self.project / "vicode.yaml").write_text(text, encoding="utf-8")

    def run_doctor(self, **overrides):
        opts = dict(
            cwd=self.tmp, project_dir=None, env=dict(os.environ), user_config_path=self.tmp / "user.yaml",
            extra_roots=(str(self.tools / "Vivado"),), include_default_roots=False, which=lambda n: None,
            timeout=30.0, work_dir=self.tmp / "work")
        opts.update(overrides)
        sink = EventSink()
        result = doctor.run_doctor(doctor.DoctorOptions(**opts), sink)
        return result, sink

    @staticmethod
    def check(result, name):
        return next((c for c in result.details["checks"] if c["name"] == name), None)


class HappyPathTests(DoctorTestCase):
    def test_ok_without_a_project(self):
        self.install()
        result, sink = self.run_doctor()
        self.assertEqual(result.vicode_exit_code, ExitCode.OK, result.details["checks"])
        self.assertEqual(result.status, "succeeded")
        self.assertEqual((result.tool_version, result.exit_code), ("2023.2", 0))
        self.assertEqual(self.check(result, "vivado_probe")["status"], "ok")
        self.assertTrue(Path(result.logs[0]).is_file())
        self.assertTrue(Path(result.artifacts[0]).is_file())
        self.assertEqual(self.check(result, "project_config")["status"], "skip")

    def test_vivado_is_started_with_explicit_log_options(self):
        self.install()
        self.run_doctor()
        call = (self.marker / "invoked.txt").read_text()
        for flag in ("-mode batch", "-source", "-log", "-journal", "-tempDir", "-notrace"):
            self.assertIn(flag, call)

    def test_file_arguments_are_short_relative_names(self):
        self.tools = self.tmp / "tools with spaces (x86)"
        self.install()
        self.run_doctor(extra_roots=(str(self.tools / "Vivado"),), work_dir=self.tmp / "work dir")
        call = (self.marker / "invoked.txt").read_text().split()
        self.assertEqual(call[call.index("-source") + 1], "environment.tcl")
        self.assertEqual(call[call.index("-log") + 1], "environment.vivado.log")
        self.assertEqual(call[call.index("-tempDir") + 1], "tmp")
        self.assertFalse(any(os.sep in a for a in call), call)

    def test_compatibility_is_reported_as_untested(self):
        self.install()
        result, _ = self.run_doctor()
        self.assertEqual(result.details["compatibility"], "untested")
        self.assertEqual(self.check(result, "compatibility")["status"], "warn")
        self.assertTrue(any("verified compatibility matrix" in d.message for d in result.diagnostics))

    def test_events_stream(self):
        self.install()
        result, sink = self.run_doctor()
        names = [e["event"] for e in sink.events]
        self.assertEqual((names[0], names[-1]), ("job.started", "job.finished"))
        stages = [e["stage"] for e in sink.events if e["event"] == "job.stage"]
        for expected in ("platform", "vivado_discovery", "vivado_probe"):
            self.assertIn(expected, stages)
        self.assertEqual(len({e["job_id"] for e in sink.events}), 1)
        self.assertTrue(all(e["protocol"] == 1 for e in sink.events))
        self.assertEqual(sink.events[-1]["result"]["operation"], "doctor")
        json.dumps(sink.events)

    def test_vivado_messages_become_diagnostics(self):
        self.install(mode="warn")
        result, _ = self.run_doctor()
        found = {(d.id, d.severity) for d in result.diagnostics if d.category == "vivado"}
        self.assertIn(("Synth 8-3332", "warning"), found)
        self.assertIn(("Vivado 12-4739", "critical_warning"), found)
        located = next(d for d in result.diagnostics if d.id == "Synth 8-3332")
        self.assertEqual((located.file, located.line), ("C:/proj/rtl/top.sv", 42))
        self.assertEqual(result.vicode_exit_code, ExitCode.OK)  # warnings do not fail the environment

    def test_paths_with_spaces(self):
        self.tools = self.tmp / "my tools (x86)"
        self.install()
        self.project = self.tmp / "my project"
        self.project.mkdir()
        self.write_project()
        result, _ = self.run_doctor(project_dir=self.project, extra_roots=(str(self.tools / "Vivado"),))
        self.assertEqual(result.vicode_exit_code, ExitCode.OK, result.details["checks"])

    def test_passes_licence_variable_but_not_other_secrets(self):
        self.install()
        env = dict(os.environ, XILINXD_LICENSE_FILE="2100@license-server", MY_SECRET_TOKEN="s3cret")
        result, sink = self.run_doctor(env=env)
        seen = (self.marker / "env_seen.txt").read_text().split("\n")
        self.assertIn("XILINXD_LICENSE_FILE", seen)
        self.assertNotIn("MY_SECRET_TOKEN", seen)
        blob = json.dumps(result.to_dict()) + json.dumps(sink.events)
        self.assertNotIn("license-server", blob)
        self.assertNotIn("s3cret", blob)

    def test_no_launch_does_not_start_vivado(self):
        self.install()
        result, _ = self.run_doctor(launch=False)
        self.assertEqual(result.vicode_exit_code, ExitCode.OK)
        self.assertEqual(self.check(result, "vivado_probe")["status"], "skip")
        self.assertFalse((self.marker / "invoked.txt").exists())
        self.assertEqual(result.tool_version, "2023.2")  # from the install path

    def test_newest_install_is_selected_and_all_are_reported(self):
        self.install(version="2022.2")
        newest = self.install(version="2024.1", probe_version="2024.1")
        result, _ = self.run_doctor()
        self.assertEqual(result.details["selected"]["launcher"], str(newest))
        self.assertEqual([i["version"] for i in result.details["installations"]], ["2024.1", "2022.2"])


class FailureTests(DoctorTestCase):
    def test_no_vivado(self):
        result, _ = self.run_doctor()
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertEqual(result.status, "failed")
        check = self.check(result, "vivado_discovery")
        self.assertEqual(check["status"], "fail")
        self.assertIn("--vivado", check["hint"])
        self.assertEqual(self.check(result, "vivado_probe")["status"], "skip")

    def test_explicit_path_never_falls_back(self):
        self.install()
        result, _ = self.run_doctor(vivado=str(self.tmp / "wrong" / "vivado"))
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertIn("not found", self.check(result, "vivado_discovery")["message"])
        self.assertFalse((self.marker / "invoked.txt").exists())

    def test_explicit_install_folder(self):
        launcher = self.install()
        result, _ = self.run_doctor(vivado=str(launcher.parent.parent), extra_roots=())
        self.assertEqual(result.vicode_exit_code, ExitCode.OK)
        self.assertEqual(result.details["vivado_setting_source"], "cli")

    def test_tcl_error_exit_status(self):
        self.install(mode="tcl_error")
        result, _ = self.run_doctor()
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("status 1", self.check(result, "vivado_probe")["message"])
        self.assertTrue(any(d.id == "Common 17-39" and d.severity == "error" for d in result.diagnostics))

    def test_exit_status_zero_is_not_proof(self):
        self.install(mode="silent_success")
        result, _ = self.run_doctor()
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("not proof", self.check(result, "vivado_probe")["message"])

    def test_hang_is_stopped_with_its_children(self):
        self.install(mode="hang")
        started = time.monotonic()
        result, _ = self.run_doctor(timeout=1.5)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertIn("did not finish", self.check(result, "vivado_probe")["message"])
        pid_file = self.tmp / "work"
        pids = list(pid_file.rglob("child.pid"))
        self.assertEqual(len(pids), 1)
        pid = int(pids[0].read_text())
        end = time.monotonic() + 10
        while jobs.pid_alive(pid) and time.monotonic() < end:
            time.sleep(0.1)
        self.assertFalse(jobs.pid_alive(pid), "Vivado's child process was left running")

    def test_cancellation(self):
        self.install(mode="hang")
        cancel = threading.Event()

        def trigger():
            end = time.monotonic() + 10
            while time.monotonic() < end and not list((self.tmp / "work").rglob("child.pid")):
                time.sleep(0.05)
            cancel.set()

        threading.Thread(target=trigger, daemon=True).start()
        result, _ = self.run_doctor(cancel=cancel, timeout=60)
        self.assertEqual(result.vicode_exit_code, ExitCode.CANCELLED)
        self.assertEqual(result.status, "cancelled")

    def test_probe_version_mismatch_is_a_warning(self):
        self.install(version="2023.2", probe_version="2024.1")
        result, _ = self.run_doctor()
        self.assertEqual(result.vicode_exit_code, ExitCode.OK)
        self.assertEqual(self.check(result, "vivado_version")["status"], "warn")
        self.assertEqual(result.tool_version, "2024.1")


class ProjectTests(DoctorTestCase):
    def test_part_available(self):
        self.install()
        self.write_project()
        result, _ = self.run_doctor(project_dir=self.project)
        self.assertEqual(result.vicode_exit_code, ExitCode.OK, result.details["checks"])
        self.assertEqual(self.check(result, "target_part")["status"], "ok")
        self.assertEqual(result.target_part, "xc7z020clg400-1")

    def test_part_missing_fails(self):
        self.install(parts=("xc7a35tcpg236-1",))
        self.write_project()
        result, _ = self.run_doctor(project_dir=self.project)
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertIn("not available", self.check(result, "target_part")["message"])

    def test_invalid_config_wins_with_exit_2(self):
        self.install()
        self.write_project("schema_version: 1\nproject:\n  name: demo\nbild: {}\n")
        result, _ = self.run_doctor(project_dir=self.project)
        self.assertEqual(result.vicode_exit_code, ExitCode.USAGE_OR_CONFIG)
        self.assertIn("unknown key", self.check(result, "project_config")["message"])

    def test_explicit_project_dir_without_manifest(self):
        self.install()
        result, _ = self.run_doctor(project_dir=self.project)
        self.assertEqual(result.vicode_exit_code, ExitCode.USAGE_OR_CONFIG)

    def test_project_found_from_subfolder_and_record_written(self):
        self.install()
        self.write_project()
        sub = self.project / "rtl" / "core"
        sub.mkdir(parents=True)
        result, _ = self.run_doctor(cwd=sub)
        self.assertEqual(result.vicode_exit_code, ExitCode.OK)
        record = self.project / "build" / "metadata" / "doctor-result.json"
        self.assertTrue(record.is_file())
        data = json.loads(record.read_text())
        self.assertEqual(data["details"]["project"]["root"], str(self.project))
        self.assertEqual(len(data["details"]["project"]["config_hash"]), 64)
        self.assertIn("revision", data["details"]["project"]["git"])
        self.assertEqual(result.logs, ["build/logs/environment.log"])
        self.assertTrue((self.project / "build" / "vivado" / "environment.tcl").is_file())
        self.assertFalse((self.project / "build" / jobs.LOCK_NAME).exists(), "lock must be released")

    def test_busy_project(self):
        self.install()
        self.write_project()
        lock = jobs.ProjectLock(self.project / "build", "synth")
        lock.acquire()
        self.addCleanup(lock.release)
        result, _ = self.run_doctor(project_dir=self.project)
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertIn("busy", self.check(result, "vivado_probe")["message"])
        self.assertFalse((self.marker / "invoked.txt").exists())

    def test_untrusted_project_cannot_choose_the_executable(self):
        self.install()
        evil = self.tmp / "evil" / "vivado"
        evil.parent.mkdir()
        evil.write_text("#!/bin/sh\ntouch " + str(self.tmp / "PWNED") + "\n")
        evil.chmod(0o755)
        self.write_project(VALID_MANIFEST.replace("executable: auto", f"executable: {evil}"))
        result, _ = self.run_doctor(project_dir=self.project)
        self.assertEqual(result.vicode_exit_code, ExitCode.OK, result.details["checks"])
        self.assertEqual(self.check(result, "vivado_setting")["status"], "warn")
        self.assertFalse((self.tmp / "PWNED").exists())
        self.assertNotEqual(result.details["selected"]["launcher"], str(evil))

    def test_trusted_project_may_choose_the_executable(self):
        launcher = self.install()
        self.write_project(VALID_MANIFEST.replace("executable: auto", f"executable: {launcher}"))
        user = self.tmp / "user.yaml"
        config.add_trusted_project(user, self.project)
        result, _ = self.run_doctor(project_dir=self.project, extra_roots=())
        self.assertEqual(result.vicode_exit_code, ExitCode.OK, result.details["checks"])
        self.assertEqual(result.details["vivado_setting_source"], "project")

    def test_user_config_executable_and_search_paths(self):
        launcher = self.install()
        user = self.tmp / "user.yaml"
        user.write_text(f"schema_version: 1\nvivado:\n  executable: {launcher}\n", encoding="utf-8")
        result, _ = self.run_doctor(extra_roots=())
        self.assertEqual(result.details["vivado_setting_source"], "user")
        self.assertEqual(result.vicode_exit_code, ExitCode.OK)
        user.write_text(f"schema_version: 1\nvivado:\n  search_paths: ['{self.tools / 'Vivado'}']\n", encoding="utf-8")
        result, _ = self.run_doctor(extra_roots=())
        self.assertEqual(result.vicode_exit_code, ExitCode.OK, result.details["checks"])

    def test_invalid_user_config(self):
        self.install()
        (self.tmp / "user.yaml").write_text("bogus: 1\n", encoding="utf-8")
        result, _ = self.run_doctor()
        self.assertEqual(result.vicode_exit_code, ExitCode.USAGE_OR_CONFIG)
