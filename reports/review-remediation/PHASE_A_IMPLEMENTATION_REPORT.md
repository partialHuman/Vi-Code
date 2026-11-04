# Phase A: Security and Crash Hardening Implementation Report

**Date:** 2026-11-02
**Branch:** `fix/foundation-review`
**Baseline Commit:** `1feb0a9eea03cb5cecede270c1db804bc4176010` (`docs: add foundation review remediation plans`)
**Tag Baseline:** `v0.1.0` (`e81f64e18a3fd333c0937d1040b1d9caad935716`)
**Status:** Implementation & Verification Complete (Pending User Review Before Commit)

---

## 1. Executive Summary

Phase A of the Vi-Code Foundation Review Remediation addresses the four confirmed P0 security and crash vulnerability findings identified in the independent review (`Vi-Code_0.1.0_Independent_Review.md`):

1. **VIC-REV-001 (High):** Untrusted Windows executable search path vulnerability.
2. **VIC-REV-002 (Medium/P0):** Arbitrary code execution via untrusted repository Git configuration (`core.fsmonitor`).
3. **VIC-REV-003 (Medium/P0):** Compatibility matrix schema fragility and crash prevention.
4. **VIC-REV-004 (Medium/P0):** Unstructured exception escape in `doctor` and CLI JSON/JSON-stream modes.

All four findings have been remediated with root-cause architectural fixes, validated through dedicated regression tests, and verified across both synthetic mock environments and live Windows 11 execution against installed Vivado 2018.2.

---

## 2. Detailed Technical Remediations

### Task P0-1 — Secure Windows Executable Search Paths (VIC-REV-001)

* **Vulnerability:**
  On Windows, `shutil.which` searches the current working directory first when `.` is present in `PATH` or under cmd/shell resolution. If a repository or working directory contained a malicious `vivado.bat` or `git.exe`, `discovery.py` or `jobs.py` prioritized it over system installations.
* **Implementation:**
  * In `src/vicode/cli.py` and `src/vicode/vivado/discovery.py`: Configured `os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")` on Windows startup to instruct Windows process creation APIs to omit the current directory from default application searches.
  * In `src/vicode/vivado/discovery.py`: Implemented `_is_untrusted_path(file_path, cwd=..., project_dir=...)` and updated `discovery.discover()`. Any candidate executable returned by `which` whose resolved real path matches or resides directly in `cwd` (`cand.parent == cwd`) or resides anywhere inside an untrusted `project_dir` is discarded. Legitimate toolchain binaries residing in subdirectories beneath CWD (e.g. `cwd/tools/bin/vivado.bat`) are preserved without false-positive rejection (resolving PA-REV-005). Explicit `--vivado` paths configured by the user remain permitted via `resolve_path()`.
  * In `src/vicode/jobs.py`: Implemented `_safe_git_command(repo_path)` to ensure the `git` binary is never resolved directly from `cwd` or the repository folder. On Windows, it verifies `shutil.which("git")` is outside `cwd`/repo, and falls back to system paths (`%ProgramFiles%\Git\cmd\git.exe`, `%ProgramFiles(x86)%\Git\cmd\git.exe`).
  * In `src/vicode/vivado/process.py`: Hardened `terminate_tree()` on Windows to invoke `%SystemRoot%\System32\taskkill.exe` directly with no unqualified fallback, failing safely to `proc.kill()` if the trusted executable is unavailable.
* **Regression Tests:**
  * `tests/test_discovery.py:DiscoverTests.test_planted_cwd_launcher_is_ignored_by_which`
  * `tests/test_discovery.py:DiscoverTests.test_planted_project_dir_launcher_is_ignored_by_which`
  * `tests/test_discovery.py:DiscoverTests.test_explicit_configured_launcher_in_cwd_is_honored`
  * `tests/test_discovery.py:DiscoverTests.test_legitimate_path_tool_beneath_cwd_is_not_rejected`
  * `tests/test_jobs.py:RecordTests.test_safe_git_command_rejects_planted_and_accepts_trusted`
  * `tests/test_process.py:RunProcessTests.test_terminate_tree_invokes_absolute_system32_taskkill_and_never_bare_taskkill`
  * `tests/test_process.py:RunProcessTests.test_terminate_tree_safe_fallback_when_taskkill_missing`

---

### Task P0-2 — Isolate Git Invocations Against Malicious Configs (VIC-REV-002)

* **Vulnerability:**
  `jobs.git_state(path)` ran `git -C <path> status --porcelain`. Cloned or downloaded untrusted repositories with a weaponized `.git/config` setting `core.fsmonitor = <malicious_script>` or `.gitattributes` clean-filter rule `filter.<name>.clean` caused Git to execute attacker-specified payload scripts during routine `vicode doctor` commands.
* **Implementation:**
  * In `src/vicode/jobs.py` (`git_state`): Enforced the project trust boundary: `git_state(path, trusted=False)` immediately returns `{"revision": None, "dirty": None}` without spawning Git for untrusted projects, preventing clean-filter execution completely (resolving PA-REV-001).
  * For explicitly trusted projects (`trusted=True`), Git is invoked with CLI configuration overrides that take precedence over repository-level `.git/config`:
    ```python
    [
        git_bin,
        "-c", "core.fsmonitor=false",
        "-c", "core.useBuiltinFSMonitor=false",
        "-c", "core.hooksPath=",
        "--no-optional-locks",
        "-C", str(path),
        *args,
    ]
    ```
  * Injected environment isolation variables: `GIT_CONFIG_NOSYSTEM=1` and `GIT_TERMINAL_PROMPT=0`.
  * In `src/vicode/doctor.py`: Propagated trust status via `config.is_trusted(root, user.config)`.
  * Note on Trusted Projects: Explicitly trusted projects (`trusted=True`) can execute repository-defined Git clean filters, as clean filters are an inherent content-filtering feature of Git executed during status queries. Documentation and CLI help describe this trust implication.
* **Regression Tests:**
  * `tests/test_jobs.py:RecordTests.test_git_state_clean_filter_execution_prevented`: Verifies positive control under unprotected `git status`, proves `jobs.git_state(trusted=False)` executes zero subprocesses, and proves `trusted=True` retrieves valid metadata.
  * `tests/test_jobs.py:RecordTests.test_git_state_defaults_to_untrusted_without_spawning_git`: Proves calling `jobs.git_state(path)` without explicit trust defaults to untrusted and produces zero subprocess invocations.
  * `tests/test_jobs.py:RecordTests.test_git_state_overrides_core_hooks_path`: Verifies that `jobs.git_state(path, trusted=True)` passes `-c core.hooksPath=` to every Git subprocess invocation.
  * `tests/test_jobs.py:RecordTests.test_git_state_ignores_core_fsmonitor_hook`: Creates a Git repository with `core.fsmonitor` pointing to a payload script and asserts that `jobs.git_state(trusted=True)` extracts revision and status without executing the monitor script.
  * `tests/test_doctor.py:ProjectTests.test_doctor_git_metadata_trust_boundary`: Asserts that `doctor` returns empty git metadata for untrusted projects and populates revision/dirty state once trusted.

---

### Task P0-3 — Harden Compatibility Matrix Schema & Error Handling (VIC-REV-003)

* **Vulnerability:**
  `compat.py:check()` assumed `data/compat_matrix.json` was always valid JSON and had a top-level dictionary with a `"verified"` list. If the file was corrupt or formatted as a JSON list `[...]` (as erroneously suggested in previous report documentation), `doctor` crashed with an uncaught `AttributeError` or `JSONDecodeError`.
* **Implementation:**
  * In `src/vicode/compat.py`: Defined `DEFAULT_MATRIX = {"schema_version": 1, "note": "...", "verified": []}` fallback and used `copy.deepcopy()` to prevent fallback dictionary mutation (resolving PA-REV-006).
  * Added `parse_matrix(raw=None)`: Validates that root JSON is a dictionary, `"verified"` is a list, and validates each entry schema (object with non-empty string `os` and `vivado`); returns `(dict, error_message)`.
  * Updated `load_matrix(raw=None)`: Guarantees an isolated valid dictionary is always returned.
  * Hardened `check(vivado_version, platform, matrix=None)`: Accepts `None`, `dict`, `str`, `list`, or arbitrary types without throwing exceptions. Validates `entry.get("status") == "verified"`. On malformed matrix data, safely degrades to status `"untested"`, preserves diagnostic error details in the returned message, and allows `doctor` to log an informative warning diagnostic without terminating or corrupting output.
* **Regression Tests:**
  * `tests/test_compat.py`: Dedicated unit test suite with 12 test methods covering valid matrix, corrupt JSON, top-level list root, missing `"verified"` key, non-list `"verified"`, entry schema validation, deep-copy isolation, package read errors, and verification matching.

---

### Task P0-4 — Structured Exception Handling in CLI & Doctor (VIC-REV-004)

* **Vulnerability:**
  Path validation exceptions (`process.UnsafeArgument`) or filesystem permission errors (`OSError`) during probe preparation escaped `doctor.py` and were caught only by `cli.py:main`'s top-level handler, which emitted unstructured plain text to `stderr` (`internal error: ...`) with no JSON or `job.finished` event on stdout.
* **Implementation:**
  * In `src/vicode/doctor.py` Stage 7: Added proactive Windows batch launcher validation:
    ```python
    if plat.is_windows and process.needs_batch_validation(selected.launcher):
        try:
            process.validate_batch_args([selected.launcher])
        except process.UnsafeArgument as exc:
            add("vivado_launcher", "fail", str(exc), "Move Vivado to a path without special characters...")
            selected = None
    ```
  * In `src/vicode/doctor.py` Stage 8: Wrapped lock acquisition and probe execution in `try / except (jobs.ProjectBusy, process.UnsafeArgument, OSError)`, translating any exception into structured `Diagnostic("error", ...)` entries and recording `state["env_failed"] = True`.
  * In `src/vicode/doctor.py`: Guarded `jobs.write_result(out_layout, result)` against `OSError`.
  * In `src/vicode/cli.py` (`_run` and `main`): Added structured exception fallback for unexpected failures. When `--json` or `--json-stream` is requested, `OperationResult` or `job.finished` JSON lines are guaranteed to be emitted to `stdout` before exiting with code 1. In text mode, internal error diagnostics are printed to `sys.stderr` without exposing sensitive environment information (resolving PA-REV-007).
* **Regression Tests:**
  * `tests/test_doctor.py:ProjectTests.test_stage_7_unsafe_launcher_batch_validation`
  * `tests/test_doctor.py:ProjectTests.test_stage_8_unsafe_argument_during_probe_execution`
  * `tests/test_doctor.py:ProjectTests.test_filesystem_oserror_during_probe_is_structured`
  * `tests/test_cli.py:DoctorCliTests.test_doctor_unsafe_argument_returns_structured_json`
  * `tests/test_cli.py:DoctorCliTests.test_doctor_unsafe_argument_returns_structured_json_stream`
  * `tests/test_cli.py:DoctorCliTests.test_cli_run_exception_fallback`
  * `tests/test_cli.py:DoctorCliTests.test_cli_main_exception_fallback`

---

## 3. Verification Evidence

### 3.1 Full Test Suite Execution

* **Command:** `.\.venv\Scripts\python -m unittest discover -s tests -t . -v`
* **Result:** `Ran 144 tests in 12.354s — OK (skipped=1)`

### 3.2 Python Development Mode & Warning Verification

* **Command:** `.\.venv\Scripts\python -X dev -W error -m unittest discover -s tests -t . -v`
* **Result:** `Ran 144 tests in 12.125s — OK (skipped=1)`
* **Significance:** Confirms zero deprecation warnings, zero unclosed file/resource warnings, and strict runtime compliance under Python 3.14.7.

### 3.3 Live Real Vivado 2018.2 Integration Test

* **Command:** `cmd /c "set VICODE_REAL_VIVADO=1&& .\.venv\Scripts\python -m unittest tests.test_integration_real_vivado -v"`
* **Result:**
  ```text
  test_doctor_with_real_vivado (tests.test_integration_real_vivado.RealVivadoTests.test_doctor_with_real_vivado) ... ok
  ----------------------------------------------------------------------
  Ran 1 test in 31.334s
  OK
  launcher: D:\Xilinx\Vivado\2018.2\bin\vivado.bat | version: 2018.2 | probe seconds: 31.265
  ```

### 3.4 Live Windows 11 CLI Smoke Tests

1. **Planted `vivado.bat` in CWD with `.` on PATH:**
   * Command: `Set-Content .\vivado.bat "@echo off"; $env:PATH = ".;" + $env:PATH; vicode doctor --no-launch --json`
   * Result: Planted `vivado.bat` was safely discarded; real Vivado at `D:\Xilinx\Vivado\2018.2\bin\vivado.bat` selected; exit code 0.
2. **Batch launcher with unsafe characters (`&`):**
   * Command: `vicode doctor --vivado "$TEMP\Tools & Co\vivado.bat" --json`
   * Result: Valid JSON emitted to `stdout` with `status: "failed"`, `vicode_exit_code: 3`, and diagnostic explaining disallowed character `&`.
3. **JSON stream with unsafe characters (`&`):**
   * Command: `vicode doctor --vivado "$TEMP\Tools & Co\vivado.bat" --json-stream`
   * Result: Valid JSONL event stream emitted to `stdout` terminating with `job.finished` event carrying full failure result.

---

## 4. Modified & Added Files Summary

| File Path | Type | Nature of Changes |
|---|---|---|
| `src/vicode/cli.py` | Source | Set `NoDefaultCurrentDirectoryInExePath`, hardened `_run` and `main` exception handling for `--json`/`--json-stream`. |
| `src/vicode/compat.py` | Source | Added `DEFAULT_MATRIX`, `parse_matrix()`, hardened `load_matrix()` and `check()` against invalid schema / corrupt JSON. |
| `src/vicode/doctor.py` | Source | Passed `project_dir`/`cwd` to discovery; validated batch launchers in Stage 7; structured probe exception handling in Stage 8; protected result record writing. |
| `src/vicode/jobs.py` | Source | Implemented `_safe_git_command()`; added `-c core.fsmonitor=false`, `-c core.useBuiltinFSMonitor=false`, `-c core.hooksPath=`, `--no-optional-locks`, and `GIT_CONFIG_NOSYSTEM=1`. |
| `src/vicode/vivado/discovery.py` | Source | Set `NoDefaultCurrentDirectoryInExePath`; implemented `_is_untrusted_path()`; filtered untrusted PATH hits inside `cwd` or `project_dir`. |
| `src/vicode/vivado/process.py` | Source | Qualified `taskkill` strictly via `%SystemRoot%\System32\taskkill.exe` with fail-safe behavior and no unqualified fallback. |
| `tests/test_compat.py` | New Test | 12 unit tests covering matrix parsing, schema error recovery, and compatibility checking. |
| `tests/test_discovery.py` | Test | Added regression tests for planted cwd/project_dir launcher rejection and explicit configured path acceptance. |
| `tests/test_doctor.py` | Test | Added regression tests for unsafe batch launcher paths and filesystem probe errors. |
| `tests/test_jobs.py` | Test | Added regression tests for `core.fsmonitor` evasion, default untrusted safety, `core.hooksPath` overrides, and mocked safe git resolution across `.exe` and `.bat`. |
| `tests/test_process.py` | Test | Added regression test proving a planted `taskkill.bat` / `taskkill.exe` in cwd is never selected. |
| `tests/test_cli.py` | Test | Added CLI regression tests for unsafe launcher `--json`, `--json-stream`, and unhandled exception JSON emission. |
| `reports/review-remediation/FINDINGS_RECONCILIATION.md` | Report | Updated status of findings VIC-REV-001 through VIC-REV-004 to Remediated with implementation and verification details. |
| `reports/review-remediation/PHASE_A_IMPLEMENTATION_REPORT.md` | New Report | This report. |

---

## 5. Constraint Compliance & Readiness

* **Branch:** `fix/foundation-review` maintained without diversion.
* **Tag `v0.1.0`:** Unmodified and points to `e81f64e18a3fd333c0937d1040b1d9caad935716`.
* **Branch `main`:** Unmodified.
* **Milestone M0 Counter Synthesis Spike:** Remains explicitly OPEN and is not claimed as complete in Phase A.
* **No Git Commits or Remote Pushes:** No commits have been made for Phase A changes; all changes remain in the working directory for review.
* **Next Steps:** Review and accept Phase A implementation; then proceed to stage and commit Phase A changes when directed.
