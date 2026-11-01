# Vi-Code 0.1.0 — Automated Test Results Report

**Date:** 2026-11-01<br>
**Project:** Vi-Code 0.1.0<br>
**Test Framework:** Python Standard Library `unittest`<br>
**Host Environment:** Windows 11 (build 26300, 64-bit), Python 3.14.7<br>
**Isolated Virtual Environment:** `C:\Users\User\Documents\Projects\Vi-Code\.venv`<br>

---

## 1. Test Suite Overview & Configuration

Vi-Code's automated test suite relies exclusively on the standard library `unittest` framework and `PyYAML`. No external runners like `pytest` are configured or required.

The test suite consists of **115 total tests** across 8 test modules:
* `tests/test_cli.py`: CLI dispatch, option parsing, `--json`, `--json-stream`, exit codes, planned commands.
* `tests/test_config.py`: Schema validation, YAML parser safety, precedence, identifier validation, user config, project trust.
* `tests/test_discovery.py`: Vivado search order, path normalization, deduplication, version extraction.
* `tests/test_doctor.py`: Full doctor checks end-to-end, synthetic contract tests using `fake_vivado.py`.
* `tests/test_integration_real_vivado.py`: Real Vivado integration test (skipped unless `VICODE_REAL_VIVADO=1`).
* `tests/test_jobs.py`: Project lock, stale lock reclamation, `pid_alive` via Windows Win32 API / ctypes, build metadata records.
* `tests/test_process.py`: Subprocess runner, batch launcher argument validation, environment variable allowlist, timeout, whole-tree termination via `taskkill`.
* `tests/test_tcl_and_messages.py`: Tcl parameter quoting, probe script generation, probe marker parser, Vivado log message regex parser.

---

## 2. Test Execution Runs & Results Summary

| Run # | Description / Command | Discovered | Passed | Skipped | Failed | Errors | Duration |
|---|---|---|---|---|---|---|---|
| **Run 1** | Standard discovery run:<br>`python -m unittest discover -s tests -t . -v` | 115 | 114 | 1 | 0 | 0 | 11.632s (elapsed 12.080s) |
| **Run 2** | Strict dev mode with warnings as errors:<br>`python -X dev -W error -m unittest discover -s tests -t . -v` | 115 | 114 | 1 | 0 | 0 | 10.712s (elapsed 11.039s) |
| **Run 3** | Repeat full discovery run (flakiness check):<br>`python -m unittest discover -s tests -t . -v` | 115 | 114 | 1 | 0 | 0 | 10.717s (elapsed 11.011s) |
| **Run 4** | Real Vivado integration test module:<br>`$env:VICODE_REAL_VIVADO="1"; python -m unittest tests.test_integration_real_vivado -v` | 1 | 1 | 0 | 0 | 0 | 2.902s |
| **Run 5** | Complete test suite including Real Vivado:<br>`$env:VICODE_REAL_VIVADO="1"; python -m unittest discover -s tests -t . -v` | 115 | 115 | 0 | 0 | 0 | 14.690s (elapsed 14.953s) |

---

## 3. Results by Test Module

| Module | Test Class / Scope | Discovered | Passed | Skipped | Failed | Notes |
|---|---|---|---|---|---|---|
| `tests.test_cli` | `BasicCliTests`, `DoctorCliTests`, `InitAndValidateTests` | 21 | 21 | 0 | 0 | Exit codes 0, 1, 2, 5 verified |
| `tests.test_config` | `MetadataTests`, `ProjectConfigTests`, `SchemaTests`, `UserConfigAndTrustTests` | 21 | 21 | 0 | 0 | Strict YAML, duplicate keys, JSON schema |
| `tests.test_discovery` | `DiscoverTests` | 11 | 11 | 0 | 0 | Windows paths, drive letters, priority order |
| `tests.test_doctor` | `DoctorUnitTests`, `ProjectTests` | 28 | 28 | 0 | 0 | End-to-end diagnostics and exit code logic |
| `tests.test_integration_real_vivado` | `RealVivadoTests` | 1 | 1 | 0* | 0 | *Skipped by default; 1 Passed when `VICODE_REAL_VIVADO=1` |
| `tests.test_jobs` | `LockTests`, `RecordTests` | 10 | 10 | 0 | 0 | Exercises Windows ctypes `OpenProcess` & `GetExitCodeProcess` |
| `tests.test_process` | `BatchArgumentTests`, `EnvironmentTests`, `RunProcessTests` | 13 | 13 | 0 | 0 | Exercises `taskkill /PID <pid> /T /F` tree termination |
| `tests.test_tcl_and_messages` | `MessageParserTests`, `TclQuoteTests` | 10 | 10 | 0 | 0 | Normalization of Windows backslashes |
| **Total** | | **115** | **115** | **0** | **0** | Clean run across all modules |

---

## 4. Detailed Run Evidence

### Run 1: Standard Discovery Run
```text
python -m unittest discover -s tests -t . -v
----------------------------------------------------------------------
Ran 115 tests in 11.632s

OK (skipped=1)
Elapsed: 12080 ms
```

### Run 2: Warnings Treated as Errors (`-X dev -W error`)
```text
python -X dev -W error -m unittest discover -s tests -t . -v
----------------------------------------------------------------------
Ran 115 tests in 10.712s

OK (skipped=1)
Elapsed: 11039 ms
```
*No warnings, deprecation notices, or unclosed file descriptors were raised.*

### Run 3: Repeat Discovery Run
```text
python -m unittest discover -s tests -t . -v
----------------------------------------------------------------------
Ran 115 tests in 10.717s

OK (skipped=1)
Elapsed: 11011 ms
```
*Results were completely identical to Run 1.*

### Run 4: Real Vivado Integration Run
```text
$env:VICODE_REAL_VIVADO = "1"
python -m unittest tests.test_integration_real_vivado -v
test_doctor_with_real_vivado (tests.test_integration_real_vivado.RealVivadoTests.test_doctor_with_real_vivado) ... ok

----------------------------------------------------------------------
Ran 1 test in 2.902s

OK

{
  "launcher": "D:\\Xilinx\\Vivado\\2018.2\\bin\\vivado.bat",
  "version": "2018.2",
  "source": "default-root"
}
tool_version: 2018.2 | probe seconds: 2.841
```

### Run 5: Full Suite with Real Vivado Active
```text
$env:VICODE_REAL_VIVADO = "1"
python -m unittest discover -s tests -t . -v
----------------------------------------------------------------------
Ran 115 tests in 14.690s

OK

{
  "launcher": "D:\\Xilinx\\Vivado\\2018.2\\bin\\vivado.bat",
  "version": "2018.2",
  "source": "default-root"
}
tool_version: 2018.2 | probe seconds: 3.334
Elapsed: 14953 ms
```

---

## 5. Failure and Traceback Analysis

* **Total Failures:** 0
* **Total Errors:** 0
* **Flaky Tests:** None. Across 3 complete runs of the full test suite and individual targeted runs, every test passed deterministically with stable execution timings.
