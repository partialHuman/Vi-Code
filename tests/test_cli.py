import json
import os
import subprocess
import sys
from pathlib import Path

from vicode import cli, config
from vicode.results import ExitCode
from tests.support import TempDirTestCase, VALID_MANIFEST, make_fake_vivado, run_cli

SRC = str(Path(__file__).resolve().parent.parent / "src")


class BasicCliTests(TempDirTestCase):
    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual((code, out.strip()), (0, "vicode 0.1.0"))

    def test_python_dash_m(self):
        done = subprocess.run([sys.executable, "-m", "vicode", "--version"], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONPATH=SRC))
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "vicode 0.1.0"))

    def test_no_command_shows_help_and_exit_2(self):
        code, out, _ = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("doctor", out)

    def test_usage_errors_exit_2(self):
        self.assertEqual(run_cli(["doctor", "--timeout", "abc"])[0], 2)
        self.assertEqual(run_cli(["frobnicate"])[0], 2)
        self.assertEqual(run_cli(["init"])[0], 2)

    def test_incomplete_nested_command(self):
        self.assertEqual(run_cli(["project"])[0], 2)
        self.assertEqual(run_cli(["hardware"])[0], 2)

    def test_planned_commands(self):
        for argv, release in ((["sim"], "0.3"), (["synth"], "0.3"), (["impl"], "0.4"), (["build"], "0.4"),
                              (["hardware", "program"], "0.6"), (["tcl", "export"], "0.2"),
                              (["source", "list"], "0.2"), (["project", "import"], "0.2"), (["clean"], "0.2")):
            code, out, _ = run_cli(argv)
            self.assertEqual(code, ExitCode.NOT_AVAILABLE, argv)
            self.assertIn(f"planned for release {release}", out, argv)
        code, out, _ = run_cli(["sim", "--json"])
        data = json.loads(out)
        self.assertEqual((data["vicode_exit_code"], data["status"]), (5, "failed"))

    def test_every_documented_command_is_registered(self):
        parser_help = run_cli(["--help"])[1]
        for name in ("doctor", "init", "project", "source", "sim", "synth", "impl", "bitstream", "build", "report",
                     "status", "cancel", "clean", "tcl", "vivado", "hardware"):
            self.assertIn(name, parser_help)


class InitAndValidateTests(TempDirTestCase):
    def test_init_creates_a_valid_workspace(self):
        code, out, _ = run_cli(["init", "blinky"], cwd=self.tmp)
        self.assertEqual(code, 0, out)
        proj = self.tmp / "blinky"
        for rel in ("vicode.yaml", ".gitignore", "README.md", "rtl", "sim", "constraints", "ip", "scripts"):
            self.assertTrue((proj / rel).exists(), rel)
        self.assertIn("build/", (proj / ".gitignore").read_text())
        code, out, _ = run_cli(["project", "validate", "--project-dir", str(proj)])
        self.assertEqual(code, 0, out)

    def test_init_with_options_round_trips(self):
        code, out, _ = run_cli(["init", "demo", "--dir", str(self.tmp / "d"), "--hdl", "VHDL", "--part", "xc7z020clg400-1",
                                "--board", "tul.com.tw:pynq-z2:part0:1.0", "--top", "demo_top", "--json"])
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertIn("vicode.yaml", data["details"]["created"])
        loaded = config.load_project(self.tmp / "d")
        self.assertTrue(loaded.ok, loaded.issues)
        self.assertEqual((loaded.config.hdl, loaded.config.part, loaded.config.board, loaded.config.top_module),
                         ("VHDL", "xc7z020clg400-1", "tul.com.tw:pynq-z2:part0:1.0", "demo_top"))

    def test_init_refuses_non_empty_folder(self):
        target = self.tmp / "taken"
        target.mkdir()
        (target / "keep.txt").write_text("precious")
        code, out, _ = run_cli(["init", "demo", "--dir", str(target)])
        self.assertEqual(code, ExitCode.FAILED)
        self.assertEqual((target / "keep.txt").read_text(), "precious")
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["keep.txt"])

    def test_init_rejects_bad_names(self):
        for bad in ("1abc", "a b", "../escape", "a/b", "x;y"):
            code, _, _ = run_cli(["init", bad, "--dir", str(self.tmp / "out")])
            self.assertEqual(code, ExitCode.USAGE_OR_CONFIG, bad)
        self.assertFalse((self.tmp / "out").exists())

    def test_validate_reports_problems(self):
        (self.tmp / "vicode.yaml").write_text("schema_version: 1\nproject:\n  name: demo\nbuild:\n  jobs: 0\n", encoding="utf-8")
        code, out, _ = run_cli(["project", "validate"], cwd=self.tmp)
        self.assertEqual(code, ExitCode.USAGE_OR_CONFIG)
        self.assertIn("build.jobs", out)

    def test_validate_without_project(self):
        code, out, _ = run_cli(["project", "validate"], cwd=self.tmp)
        self.assertEqual(code, ExitCode.USAGE_OR_CONFIG)
        self.assertIn("no vicode.yaml", out)

    def test_validate_json(self):
        (self.tmp / "vicode.yaml").write_text(VALID_MANIFEST, encoding="utf-8")
        code, out, _ = run_cli(["project", "validate", "--json"], cwd=self.tmp)
        data = json.loads(out)
        self.assertEqual((code, data["status"], data["target_part"]), (0, "succeeded", "xc7z020clg400-1"))
        self.assertEqual(data["details"]["resolved"]["build"]["jobs"], 4)

    def test_json_stream_is_valid_jsonl(self):
        (self.tmp / "vicode.yaml").write_text("schema_version: 1\nproject:\n  name: demo\nzzz: 1\n", encoding="utf-8")
        code, out, _ = run_cli(["project", "validate", "--json-stream"], cwd=self.tmp)
        events = [json.loads(line) for line in out.splitlines()]
        self.assertEqual((events[0]["event"], events[-1]["event"]), ("job.started", "job.finished"))
        self.assertTrue(any(e["event"] == "job.message" and "zzz" in e["message"] for e in events))
        self.assertEqual(events[-1]["vicode_exit_code"], code)
        self.assertEqual(events[-1]["result"]["operation"], "project.validate")

    def test_trust_command(self):
        proj = self.tmp / "p"
        proj.mkdir()
        (proj / "vicode.yaml").write_text(VALID_MANIFEST, encoding="utf-8")
        user = self.tmp / "cfg" / "user.yaml"
        for _ in range(2):  # idempotent
            code, out, _ = run_cli(["project", "trust", "--project-dir", str(proj)], env={"VICODE_USER_CONFIG": str(user)})
            self.assertEqual(code, 0, out)
        loaded = config.load_user(user)
        self.assertEqual(len(loaded.config.trusted_projects), 1)
        self.assertTrue(config.is_trusted(proj, loaded.config))
        code, _, _ = run_cli(["project", "trust"], cwd=self.tmp, env={"VICODE_USER_CONFIG": str(user)})
        self.assertEqual(code, ExitCode.USAGE_OR_CONFIG)


class DoctorCliTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.launcher = make_fake_vivado(self.tmp / "tools")
        self.env = {"XILINX_VIVADO": str(self.launcher.parent.parent),
                    "VICODE_USER_CONFIG": str(self.tmp / "user.yaml")}

    def test_doctor_text(self):
        code, out, _ = run_cli(["doctor"], cwd=self.tmp, env=self.env)
        self.assertEqual(code, 0, out)
        self.assertIn("[ OK ] vivado_probe", out)
        self.assertIn("doctor: environment is ready", out)
        self.assertTrue(out.isascii(), "console output must be ASCII for Windows consoles")

    def test_doctor_json(self):
        code, out, _ = run_cli(["doctor", "--json"], cwd=self.tmp, env=self.env)
        data = json.loads(out)
        self.assertEqual((code, data["operation"], data["status"], data["tool_version"]), (0, "doctor", "succeeded", "2023.2"))
        self.assertEqual(data["protocol"], 1)

    def test_doctor_json_stream(self):
        code, out, _ = run_cli(["doctor", "--json-stream"], cwd=self.tmp, env=self.env)
        events = [json.loads(l) for l in out.splitlines()]
        self.assertEqual(events[-1]["event"], "job.finished")
        self.assertEqual(events[-1]["result"]["tool_version"], "2023.2")
        self.assertTrue(all(e["protocol"] == 1 for e in events))

    def test_doctor_explicit_vivado_and_no_launch(self):
        code, out, _ = run_cli(["doctor", "--vivado", str(self.launcher), "--no-launch", "--json"], cwd=self.tmp,
                               env={"VICODE_USER_CONFIG": str(self.tmp / "u.yaml"), "XILINX_VIVADO": ""})
        data = json.loads(out)
        self.assertEqual(code, 0, out)
        self.assertEqual(next(c for c in data["details"]["checks"] if c["name"] == "vivado_probe")["status"], "skip")

    def test_doctor_exit_codes(self):
        bad = {"VICODE_USER_CONFIG": str(self.tmp / "u.yaml"), "XILINX_VIVADO": "", "PATH": str(self.tmp)}
        code, out, _ = run_cli(["doctor", "--vivado", str(self.tmp / "missing")], cwd=self.tmp, env=bad)
        self.assertEqual(code, ExitCode.ENVIRONMENT, out)
        (self.tmp / "vicode.yaml").write_text("schema_version: 1\n", encoding="utf-8")
        code, out, _ = run_cli(["doctor", "--no-launch"], cwd=self.tmp, env=self.env)
        self.assertEqual(code, ExitCode.USAGE_OR_CONFIG, out)
