# Vi-Code 0.1.0 — Release Evidence & Traceability Plan

**Date:** 2026-11-02
**Baseline Git Tag:** `v0.1.0`
**Baseline Commit Hash:** `e81f64e18a3fd333c0937d1040b1d9caad935716`
**Target Environment:** Windows 11 (build 26300, 64-bit), Vivado 2018.2
**Requirement Ref:** VIC-REV-007, VIC-REV-009, Architecture Revision 1.1 §17

---

## 1. Release Artifact Hashes & Traceability

All release artifacts, test reports, and verification evidence are cryptographically bound to the tagged baseline commit:

| Artifact | Path | Size | SHA-256 Checksum |
|---|---|---|---|
| **Git Baseline Tag** | `refs/tags/v0.1.0` | — | `e81f64e18a3fd333c0937d1040b1d9caad935716` |
| **Initial Wheel Package** | `dist/vicode-0.1.0-py3-none-any.whl` | 34,518 bytes | `1f302e9a59c866d5b8c3add22f6ccbe2d040c1ff26dd536e1817bf26b861ea5f` |
| **Clean Built Wheel** | `reports/.../vicode-0.1.0-py3-none-any.whl` | 34,559 bytes | Derived from clean `python -m build` (contains zip file timestamp metadata) |

---

## 2. Test Result Evidence Mapping

All test results recorded in `reports/local-windows-test/TEST_RESULTS.md` map to the 0.1.0 baseline as follows:

* **Commit Verified:** `e81f64e`
* **Python Runtime:** Python 3.14.7 (64-bit), Windows AMD64
* **Dependencies:** `PyYAML 6.0.3` (`pyyaml-6.0.3-cp314-cp314-win_amd64.whl`)
* **Test Suite Discovered:** 115 tests across 8 modules
* **Standard Run:** 114 passed, 1 skipped (`test_doctor_with_real_vivado`), 0 failed (11.63s)
* **Dev Mode (`-X dev -W error`):** 114 passed, 1 skipped, 0 warnings (10.71s)
* **Real Vivado Run (`VICODE_REAL_VIVADO=1`):** 115 passed, 0 skipped, 0 failed (14.69s)

---

## 3. Compatibility Matrix Schema Update

To resolve VIC-REV-003 and adhere strictly to `compat.py` dictionary loading, `src/vicode/data/compat_matrix.json` is defined in its canonical JSON object schema:

```json
{
  "schema_version": 1,
  "note": "Only combinations that were actually run on real Windows 11 + Vivado installations belong here (milestone M0).",
  "verified": [
    {
      "os": "windows-11",
      "vivado": "2018.2",
      "status": "verified",
      "scope": [
        "doctor: discovery",
        "doctor: batch Tcl probe",
        "doctor: get_parts",
        "spike: counter synthesis"
      ],
      "evidence": "Windows 11 build 26300, Python 3.14.7, Vivado 2018.2 (SW Build 2258646), verified 2026-11-01; commit e81f64e",
      "not_verified": [
        "implementation",
        "simulation",
        "hardware programming",
        "other Vivado versions"
      ]
    }
  ]
}
```

---

## 4. Windows Smoke-Test Automation (`scripts/windows_smoke.ps1`)

To replace manual CLI verification with a repeatable, automated test script (resolving VIC-REV-007), `scripts/windows_smoke.ps1` is defined.

### 4.1 Script Specification
1. **Isolated User Config:** Sets `$env:VICODE_USER_CONFIG = "$tempDir\user_config.yaml"` so user trust operations never pollute `%APPDATA%\vicode\config.yaml`.
2. **Temporary Test Workspace:** Creates a fresh isolated directory in `$env:TEMP\vicode_smoke_<guid>` and cleans up on exit.
3. **Execution of 39 Test Scenarios:**
   * Global options (`--version`, `--help`)
   * Usage errors (no command, invalid command, planned command exit 5)
   * Project creation (`init` with options, invalid names, non-empty folders, paths with spaces)
   * Project validation (`project validate` normal, with `--json`, outside project, unknown keys, duplicate keys, invalid schema versions)
   * Project trust (`project trust` inside project, outside project, JSON output)
   * Doctor checks (`doctor --no-launch` text, JSON, JSON stream; non-existent Vivado exit 3; config error precedence exit 2; real Vivado probe; valid part; invalid part; timeout cleanup)
4. **Validation:** Checks both exit code and parses JSON/JSON-lines output to confirm structural validity.
5. **Report Generation:** Generates a summary log and exits with code 0 on complete pass or non-zero on failure.
