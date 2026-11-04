"""Tests for M0 thin end-to-end verification spike (spike.py and m0_counter_spike.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import make_fake_vivado
from vicode.jobs import build_layout
from vicode.results import ExitCode
from vicode.vivado import spike


class SpikeUnitTests(unittest.TestCase):
    def test_generate_counter_rtl(self):
        rtl = spike.generate_counter_rtl(width=8)
        self.assertIn("module counter", rtl)
        self.assertIn("parameter WIDTH = 8", rtl)
        self.assertIn("input  wire             clk", rtl)
        self.assertIn("input  wire             rst", rtl)
        self.assertIn("input  wire             en", rtl)
        self.assertIn("output reg  [WIDTH-1:0] count", rtl)
        self.assertIn("count <= count + 1'b1", rtl)

    def test_generate_synth_script_variables_and_catch_handling(self):
        with tempfile.TemporaryDirectory() as td:
            layout = build_layout(Path(td))
            script = spike.generate_synth_script(
                layout=layout,
                rtl_path=layout.root / "rtl" / "counter.v",
                dcp_path=layout.artifacts / "spike_counter_synth.dcp",
                rpt_path=layout.reports / "spike_counter_utilization.rpt",
                part="xc7a35tcpg236-1",
            )
            # 1. Explicit variable initialization
            self.assertIn("set vicode_proj_name", script)
            self.assertIn("set vicode_proj_dir", script)
            self.assertIn("set vicode_part", script)
            self.assertIn("set vicode_top", script)
            self.assertIn("set vicode_rtl", script)
            self.assertIn("set vicode_dcp_out", script)
            self.assertIn("set vicode_rpt_out", script)

            # 2. Integer-based catch block and error preservation
            self.assertIn("set vicode_code [catch {", script)
            self.assertIn("} vicode_msg]", script)
            self.assertIn("puts \"ERROR: $vicode_msg\"", script)
            self.assertIn("exit $vicode_code", script)

            # 3. Unconditional close_project attempt
            self.assertIn("catch { close_project }", script)

            # 4. Project Mode synthesis commands
            self.assertIn("create_project -force $vicode_proj_name", script)
            self.assertIn("add_files -norecurse $vicode_rtl", script)
            self.assertIn("set_property top $vicode_top [current_fileset]", script)
            self.assertIn("update_compile_order -fileset sources_1", script)
            self.assertIn("reset_run synth_1", script)
            self.assertIn("launch_runs synth_1 -jobs 1", script)
            self.assertIn("wait_on_run synth_1", script)
            self.assertIn("get_property STATUS [get_runs synth_1]", script)
            self.assertIn("get_property PROGRESS [get_runs synth_1]", script)
            self.assertIn("open_run synth_1", script)
            self.assertIn("report_utilization -file $vicode_rpt_out", script)
            self.assertIn("write_checkpoint -force $vicode_dcp_out", script)

    def test_parse_utilization_report_valid(self):
        with tempfile.TemporaryDirectory() as td:
            rpt_file = Path(td) / "utilization.rpt"
            rpt_file.write_text(
                "| Slice LUTs*             |    8 |     0 |     20800 |  0.04 |\n"
                "| Slice Registers         |    8 |     0 |     41600 |  0.02 |\n"
                "| Bonded IOB              |   10 |     0 |       106 |  9.43 |\n"
                "| BUFGCTRL                |    1 |     0 |        32 |  3.13 |\n",
                encoding="utf-8",
            )
            metrics = spike.parse_utilization_report(rpt_file)
            self.assertEqual(metrics.get("slice_luts"), 8)
            self.assertEqual(metrics.get("slice_registers"), 8)
            self.assertEqual(metrics.get("bonded_iob"), 10)
            self.assertEqual(metrics.get("bufg"), 1)

    def test_parse_utilization_report_bufg_and_bufgctrl(self):
        with tempfile.TemporaryDirectory() as td:
            # Test BUFG variant
            rpt_bufg = Path(td) / "bufg.rpt"
            rpt_bufg.write_text("| BUFG                    |    2 |     0 |        32 |  6.25 |\n", encoding="utf-8")
            metrics1 = spike.parse_utilization_report(rpt_bufg)
            self.assertEqual(metrics1.get("bufg"), 2)

            # Test BUFGCTRL variant
            rpt_bufgctrl = Path(td) / "bufgctrl.rpt"
            rpt_bufgctrl.write_text("| BUFGCTRL                |    3 |     0 |        32 |  9.38 |\n", encoding="utf-8")
            metrics2 = spike.parse_utilization_report(rpt_bufgctrl)
            self.assertEqual(metrics2.get("bufg"), 3)

    def test_parse_utilization_report_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            missing_path = Path(td) / "nonexistent.rpt"
            metrics = spike.parse_utilization_report(missing_path)
            self.assertEqual(metrics, {})

    def test_parse_utilization_report_zero_byte_file(self):
        with tempfile.TemporaryDirectory() as td:
            empty_path = Path(td) / "empty.rpt"
            empty_path.write_text("", encoding="utf-8")
            metrics = spike.parse_utilization_report(empty_path)
            self.assertEqual(metrics, {})

    def test_parse_utilization_report_unparsed_metrics_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            partial_path = Path(td) / "partial.rpt"
            partial_path.write_text(
                "| LUT as Logic            |    5 |     0 |     20800 |  0.02 |\n",
                encoding="utf-8",
            )
            metrics = spike.parse_utilization_report(partial_path)
            self.assertEqual(metrics.get("slice_luts"), 5)
            self.assertNotIn("slice_registers", metrics)
            self.assertNotIn("bufg", metrics)
            self.assertNotIn("bonded_iob", metrics)

    def test_validate_part_format(self):
        self.assertTrue(spike.validate_part_format("xc7a35tcpg236-1"))
        self.assertTrue(spike.validate_part_format("xc7z020clg400-1"))
        self.assertTrue(spike.validate_part_format("xcku040-ffva1156-2-e"))
        self.assertFalse(spike.validate_part_format(""))
        self.assertFalse(spike.validate_part_format("xc7a35t; rm -rf"))
        self.assertFalse(spike.validate_part_format("xc7a35t cpg236"))
        self.assertFalse(spike.validate_part_format("xc7a35t$foo"))


class SpikeRunnerFakeVivadoTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.vivado_root = self.root / "fake_vivado_root"
        self.proj_dir = self.root / "test_project"
        self.parts = ("xc7a35tcpg236-1", "xc7z020clg400-1")

    def tearDown(self):
        self.td.cleanup()

    def make_launcher(self, mode: str = "spike_ok") -> Path:
        return make_fake_vivado(self.vivado_root, version="2018.2", mode=mode, parts=self.parts)

    def test_spike_success_positive_control(self):
        launcher = self.make_launcher("spike_ok")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher), part="xc7a35tcpg236-1")

        self.assertEqual(result.vicode_exit_code, ExitCode.OK)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.tool_version, "2018.2")
        self.assertEqual(result.target_part, "xc7a35tcpg236-1")
        self.assertEqual(result.details.get("run_status"), "synth_design Complete!")
        self.assertEqual(result.details.get("run_progress"), "100%")

        # Checkpoint and report artifacts
        self.assertEqual(len(result.artifacts), 1)
        self.assertTrue(Path(result.artifacts[0]).is_file())
        self.assertGreater(Path(result.artifacts[0]).stat().st_size, 0)

        self.assertEqual(len(result.reports), 1)
        self.assertTrue(Path(result.reports[0]).is_file())
        self.assertGreater(Path(result.reports[0]).stat().st_size, 0)

        # Utilization details parsed
        util = result.details.get("utilization", {})
        self.assertEqual(util.get("slice_luts"), 8)
        self.assertEqual(util.get("slice_registers"), 8)
        self.assertEqual(util.get("bufg"), 1)

        # Metadata result written to disk
        meta_file = self.proj_dir / "build" / "metadata" / "spike-synth-result.json"
        self.assertTrue(meta_file.is_file())
        saved_data = json.loads(meta_file.read_text(encoding="utf-8"))
        self.assertEqual(saved_data["status"], "succeeded")
        self.assertEqual(saved_data["vicode_exit_code"], 0)

    def test_spike_stale_artifact_rejection(self):
        # Step 1: Successful run creates artifacts
        launcher_ok = self.make_launcher("spike_ok")
        res1 = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher_ok), part="xc7a35tcpg236-1")
        self.assertEqual(res1.status, "succeeded")
        dcp_file = Path(res1.artifacts[0])
        rpt_file = Path(res1.reports[0])
        self.assertTrue(dcp_file.is_file())
        self.assertTrue(rpt_file.is_file())

        # Step 2: Failed run on same directory must clean stale artifacts before run
        # and must not report stale artifacts from Step 1
        launcher_fail = make_fake_vivado(self.root / "fake_vivado_fail", version="2018.2", mode="spike_fail_run", parts=self.parts)
        res2 = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher_fail), part="xc7a35tcpg236-1")

        self.assertEqual(res2.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(res2.status, "failed")
        self.assertEqual(res2.artifacts, [])
        self.assertEqual(res2.reports, [])
        self.assertFalse(dcp_file.is_file())
        self.assertFalse(rpt_file.is_file())

        # Persisted result in metadata reflects failure
        meta_file = self.proj_dir / "build" / "metadata" / "spike-synth-result.json"
        saved = json.loads(meta_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "failed")

    def test_spike_fails_when_run_status_incomplete(self):
        launcher = self.make_launcher("spike_incomplete_status")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("STATUS='synth_design Failed!'", result.summary)

    def test_spike_fails_when_run_progress_incomplete(self):
        launcher = self.make_launcher("spike_incomplete_progress")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("PROGRESS='80%'", result.summary)

    def test_spike_fails_when_checkpoint_missing(self):
        launcher = self.make_launcher("spike_missing_dcp")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("checkpoint was not generated", result.summary)

    def test_spike_fails_when_checkpoint_zero_bytes(self):
        launcher = self.make_launcher("spike_zero_byte_dcp")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("checkpoint is empty (0 bytes)", result.summary)

    def test_spike_fails_when_checkpoint_stale_timestamp(self):
        launcher = self.make_launcher("spike_stale_dcp")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("checkpoint is stale", result.summary)

    def test_spike_fails_when_report_missing(self):
        launcher = self.make_launcher("spike_missing_rpt")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("utilization report was not generated", result.summary)

    def test_spike_fails_when_report_zero_bytes(self):
        launcher = self.make_launcher("spike_zero_byte_rpt")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("utilization report is empty (0 bytes)", result.summary)

    def test_spike_fails_when_report_stale_timestamp(self):
        launcher = self.make_launcher("spike_stale_rpt")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("utilization report is stale", result.summary)

    def test_spike_fails_when_part_format_invalid(self):
        launcher = self.make_launcher("spike_ok")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher), part="invalid part; rm -rf")
        self.assertEqual(result.vicode_exit_code, ExitCode.USAGE_OR_CONFIG)
        self.assertEqual(result.status, "failed")
        self.assertIn("invalid target FPGA part", result.summary)

    def test_spike_fails_when_part_not_installed(self):
        launcher = self.make_launcher("spike_part_unavailable")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher), part="xc7a35tcpg236-1")
        self.assertEqual(result.vicode_exit_code, ExitCode.USAGE_OR_CONFIG)
        self.assertEqual(result.status, "failed")
        self.assertIn("not available in Vivado installation", result.summary)

    def test_spike_fails_when_vivado_process_exits_nonzero(self):
        launcher = self.make_launcher("tcl_error")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher))
        self.assertEqual(result.vicode_exit_code, ExitCode.FAILED)
        self.assertEqual(result.status, "failed")
        self.assertIn("failed with exit code 1", result.summary)

    def test_spike_fails_when_vivado_not_found(self):
        fake_missing = self.root / "nonexistent_vivado" / "bin" / ("vivado.bat" if os.name == "nt" else "vivado")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(fake_missing))
        self.assertEqual(result.vicode_exit_code, ExitCode.ENVIRONMENT)
        self.assertEqual(result.status, "failed")
        self.assertIn("not found", result.summary)

    def test_spike_timeout_failure(self):
        launcher = self.make_launcher("hang")
        result = spike.run_spike(root=self.proj_dir, vivado_bin=str(launcher), timeout=0.5)
        self.assertEqual(result.vicode_exit_code, ExitCode.CANCELLED)
        self.assertEqual(result.status, "cancelled")
        self.assertIn("timed out", result.summary)

    def test_spike_cli_script_execution(self):
        launcher = self.make_launcher("spike_ok")
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "m0_counter_spike.py"

        proc = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--project-dir",
                str(self.proj_dir),
                "--vivado",
                str(launcher),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["protocol"], 1)
        self.assertEqual(data["operation"], "spike-synth")
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(data["vicode_exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
