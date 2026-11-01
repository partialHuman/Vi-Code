"""Opt-in checks against a REAL Vivado installation (milestone M0 evidence).

Skipped unless VICODE_REAL_VIVADO=1. Run on the Windows 11 machine that has Vivado:

    set VICODE_REAL_VIVADO=1
    python -m unittest tests.test_integration_real_vivado -v
"""
import json
import os
import unittest

from tests.support import run_cli

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
