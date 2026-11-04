"""Opt-in checks against a REAL Vivado installation (milestone M0 evidence).

Skipped unless VICODE_REAL_VIVADO=1. Run on the Windows 11 machine that has Vivado:

    set VICODE_REAL_VIVADO=1
    python -m unittest tests.test_integration_real_vivado -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.support import run_cli
from vicode.vivado.spike import run_spike

REAL = os.environ.get("VICODE_REAL_VIVADO") == "1"


@unittest.skipUnless(REAL, "set VICODE_REAL_VIVADO=1 to run against a real Vivado installation")
class RealVivadoTests(unittest.TestCase):
    def test_doctor_with_real_vivado(self):
        code, out, _ = run_cli(["doctor", "--json", "--timeout", "300"])
        data = json.loads(out)
        print("\n" + json.dumps(data["details"].get("selected"), indent=2))
        print("tool_version:", data["tool_version"], "| probe seconds:", data["details"].get("probe_seconds"))
        self.assertEqual(code, 0, json.dumps(data["details"]["checks"], indent=2))
        self.assertEqual(data["status"], "succeeded")
        self.assertTrue(data["tool_version"])

    def test_counter_synthesis_with_real_vivado(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            result = run_spike(root=project_dir, part="xc7a35tcpg236-1", timeout=600)
            print("\nReal Vivado Synthesis Result:")
            print("Status:", result.status)
            print("Summary:", result.summary)
            print("Tool Version:", result.tool_version)
            print("Target Part:", result.target_part)
            print("Artifacts:", result.artifacts)
            print("Reports:", result.reports)
            print("Utilization:", json.dumps(result.details.get("utilization"), indent=2))

            self.assertEqual(result.vicode_exit_code, 0, result.summary)
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.tool_version, "2018.2")
            self.assertEqual(result.target_part, "xc7a35tcpg236-1")
            self.assertEqual(result.details.get("run_status"), "synth_design Complete!")
            self.assertEqual(result.details.get("run_progress"), "100%")

            self.assertEqual(len(result.artifacts), 1)
            dcp_path = Path(result.artifacts[0])
            self.assertTrue(dcp_path.is_file())
            self.assertGreater(dcp_path.stat().st_size, 0)

            self.assertEqual(len(result.reports), 1)
            rpt_path = Path(result.reports[0])
            self.assertTrue(rpt_path.is_file())
            self.assertGreater(rpt_path.stat().st_size, 0)

            # Assert parsed utilization numbers exist
            util = result.details.get("utilization", {})
            self.assertIn("slice_luts", util)
            self.assertIn("slice_registers", util)
            self.assertGreaterEqual(util["slice_luts"], 1)
            self.assertGreaterEqual(util["slice_registers"], 1)

            # Assert metadata result JSON exists and is valid
            meta_path = project_dir / "build" / "metadata" / "spike-synth-result.json"
            self.assertTrue(meta_path.is_file())
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(data["protocol"], 1)
            self.assertEqual(data["status"], "succeeded")
            self.assertEqual(data["operation"], "spike-synth")
