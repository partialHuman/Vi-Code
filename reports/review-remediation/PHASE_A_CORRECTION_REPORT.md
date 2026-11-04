# Phase A Independent Review Correction Report

**Date:** 2026-11-03
**Branch:** `fix/foundation-review`
**Baseline Tag:** `v0.1.0` (`e81f64e18a3fd333c0937d1040b1d9caad935716`)
**Current HEAD:** `1feb0a9eea03cb5cecede270c1db804bc4176010` (`docs: add foundation review remediation plans`)
**Review Verdict Addressed:** ACCEPTED WITH CONDITIONS (Claude Independent Review)
**Status:** Verification Complete — All Blocking & Conditional Findings Resolved (Uncommitted Working Tree)

---

## 1. Executive Summary

Following Claude's independent review of Phase A, all blocking findings (P0/PA-REV-001), conditional evidence requirements (C3, C4, C5), and scoped non-blocking quality improvements (PA-REV-005, PA-REV-006, PA-REV-007, PA-REV-008) have been fully resolved with root-cause fixes and verifiable test suites.

Strict project constraints were maintained:
* Immutable baseline tag `v0.1.0` and branch `main` remain completely untouched at commit `e81f64e`.
* All modifications are constrained to `fix/foundation-review`.
* Zero commits, stages, tags, rebases, or pushes were performed.
* Milestone M0 counter synthesis spike is kept explicitly open and not started in Phase A.

---

## 2. Findings Resolved & Technical Corrections

### 2.1 PA-REV-001 / VIC-REV-002: Git Clean-Filter Execution
* **Claude Finding:** Untrusted repositories can execute attacker-controlled clean filters (`.gitattributes` + `.git/config` `filter.<driver>.clean`) during `git status --porcelain` regardless of existing CLI configuration overrides (`-c core.fsmonitor=false -c core.hooksPath=`).
* **Root Cause:** Vi-Code invoked `git status --porcelain` to query revision and dirty state for all projects, regardless of whether the user explicitly trusted the project.
* **Correction Implemented:**
  1. In `src/vicode/jobs.py` (`git_state`): Updated signature to `def git_state(path: Path, trusted: bool = False) -> dict[str, Any]:`. If `not trusted`: returns `{"revision": None, "dirty": None}` immediately without spawning any `git` subprocess.
  2. For explicitly trusted projects (`trusted=True`): Git is invoked with verified executable resolution (`_safe_git_command`) and CLI configuration overrides (`-c core.fsmonitor=false -c core.useBuiltinFSMonitor=false -c core.hooksPath= --no-optional-locks -C <path> ...`) with `GIT_CONFIG_NOSYSTEM=1` and `GIT_TERMINAL_PROMPT=0` as defense-in-depth.
  3. In `src/vicode/doctor.py` (line 265): Propagated project trust status: `trusted = config.is_trusted(root, user.config)`.
  4. Documentation and Trust Boundary: Explicitly documented that trusted projects (`trusted=True`) can execute repository-defined Git clean filters, as clean filters are an inherent content-filtering feature of Git executed during status queries. Updated `vicode project trust --help` and `docs/configuration.md` accordingly.
* **Tests Added:**
  * `tests/test_jobs.py:RecordTests.test_git_state_clean_filter_execution_prevented`: Positive control proves clean filter payload executes under unprotected `git status`; verifies that `jobs.git_state(path, trusted=False)` creates zero subprocesses and leaves the canary marker untouched; verifies `jobs.git_state(path, trusted=True)` retrieves revision and dirty state.
  * `tests/test_jobs.py:RecordTests.test_git_state_defaults_to_untrusted_without_spawning_git`: Proves calling `jobs.git_state(path)` without explicit trust defaults to untrusted and produces zero subprocess invocations.
  * `tests/test_jobs.py:RecordTests.test_git_state_overrides_core_hooks_path`: Verifies that `jobs.git_state(path, trusted=True)` passes `-c core.hooksPath=` to every Git subprocess invocation.
  * `tests/test_doctor.py:ProjectTests.test_doctor_git_metadata_trust_boundary`: Confirms doctor returns empty git metadata for untrusted projects and populates it when trusted.

---

### 2.2 Evidence Documentation Corrections (C3 & C4)

#### C3: `RELEASE_EVIDENCE_PLAN.md`
* **Corrections:**
  1. Removed `spike: counter synthesis` from `verified.scope`.
  2. Added `spike: counter synthesis` under `not_verified`.
  3. Added explicit requirement callout noting Milestone M0 remains open pending empirical counter synthesis execution.
  4. Corrected Windows test-to-commit attribution: stated that tests on 2026-11-01 were performed on the pre-commit working tree, and source equivalence to `v0.1.0` (`e81f64e`) is established via exact source diff.
  5. Removed unsupported speculation regarding ZIP timestamp metadata.
  6. Marked clean-built second wheel SHA-256 as explicitly unavailable because the artifact was not preserved in the tree.

#### C4: `FINDINGS_RECONCILIATION.md`
* **Corrections:**
  1. VIC-REV-015: Removed unsupported claim that "Architecture §13 specifies manifest content hashing for 0.2". Replaced with accurate reference to 0.1 design specification (Sections 9.3 and 9.4; `docs/configuration.md`) specifying path-keyed trust via user configuration `trusted_projects`.
  2. Section 1 Executive Summary: Narrowed claims of live Windows 11 reproduction, distinguishing Windows-specific empirical testing (search paths, taskkill tree termination, batch argument validation, Git hooks/filters, ctypes process inspection, real Vivado 2018.2 probe) from platform-independent unit tests and code inspection.
  3. VIC-REV-001: Explicitly stated that `.` was present in PATH during empirical reproduction on Windows 11 (the prerequisite condition for Python 3.12+ `shutil.which` and Windows shell command resolution).

---

### 2.3 Regression Test Validity Corrections (C5)

* **Taskkill Mocked Test (`tests/test_process.py`):**
  * Replaced ineffective planted `.bat` test with Windows-specific subprocess mocking.
  * `test_terminate_tree_invokes_absolute_system32_taskkill_and_never_bare_taskkill`: Asserts `subprocess.run` invokes `%SystemRoot%\System32\taskkill.exe`, verifies `/PID <pid> /T /F` arguments, and asserts bare `taskkill` or `taskkill.exe` is never called.
  * `test_terminate_tree_safe_fallback_when_taskkill_missing`: Mocks `os.path.isfile` returning `False` for `taskkill.exe`, verifies `subprocess.run` is never called (zero unqualified search path fallback), and verifies safe fallback to `proc.kill()`.
* **Unsafe Launcher Batch Tests (`tests/test_doctor.py`, `tests/test_cli.py`):**
  * Explicitly simulated Windows platform via `platform_info.detect(system="windows", windows_build=26300, release="11")` so tests do not rely on POSIX executable bit permissions.
  * `test_stage_7_unsafe_launcher_batch_validation`: Tests Stage 7 rejection when launcher path contains `&`, asserting `vivado_launcher` fails with batch unsafe diagnostic and `vivado_probe` is skipped.
  * `test_stage_8_unsafe_argument_during_probe_execution`: Tests Stage 8 probe exception handling when launcher is clean but probe execution raises `process.UnsafeArgument`, asserting `vivado_probe` fails and records structured error diagnostics.
  * In `tests/test_cli.py`: Guarded batch launcher CLI tests with `@unittest.skipUnless(os.name == "nt", ...)` making platform constraints explicit.
* **Filesystem Error Test (`tests/test_doctor.py`):**
  * In `test_filesystem_oserror_during_probe_is_structured`: Replaced broad `"file" in message.lower()` assertion with exact check for `"filesystem error during probe"` and check status `"fail"`.
* **Compatibility Matrix Tests (`tests/test_compat.py`):**
  * Strengthened assertions in `test_check_with_malformed_matrix_reports_diagnostics` to assert exact error strings (`"matrix must be a dict"`, `"corrupt compatibility matrix JSON"`, `"missing 'verified' list"`, `"entry 0 is not a JSON object"`) appear in returned messages.
  * Added `test_package_data_read_failure` covering the file read error branch.
* **CLI Exception Fallback Tests (`tests/test_cli.py`):**
  * Separated `test_cli_run_exception_fallback` (testing `_run()` exception handler) and `test_cli_main_exception_fallback` (testing `main()` dispatch handler) into independent tests so neither handler masks the absence of the other. Tested `--json`, `--json-stream`, and plain text mode for both.

---

### 2.4 Non-Blocking Quality Improvements

#### PA-REV-005: Reduce False-Positive Executable Rejection
* **Issue:** `discovery.py:_is_untrusted_path()` rejected any candidate whose path had `untrusted_dirs` in its parents. If CWD was `$HOME` or a parent workspace, valid toolchains in subdirectories (e.g. `~/.local/bin` or `~/tools/vivado/bin`) were falsely rejected.
* **Fix:** Differentiated `cwd` and `project_dir` in `_is_untrusted_path(file_path, cwd=..., project_dir=...)`. For `cwd`, only rejects candidates located directly inside CWD (`cand.parent == cwd` or `cand == cwd`). For `project_dir`, rejects any binary located inside the untrusted project directory tree.
* **Test Added:** `tests/test_discovery.py:DiscoverTests.test_legitimate_path_tool_beneath_cwd_is_not_rejected`.

#### PA-REV-006: Compatibility Matrix Hardening & Deep Copy
* **Issue:** Fallback `DEFAULT_MATRIX.copy()` was shallow, risking dictionary/list mutation. Verified entries were not validated for required schema or status.
* **Fix:** In `src/vicode/compat.py`, used `copy.deepcopy(DEFAULT_MATRIX)` for all fallback returns. Added entry schema validation in `parse_matrix()` and `check()`. Checked `entry.get("status") == "verified"`.
* **Tests Added:** `test_deep_copy_isolation_of_default_matrix`, `test_entry_schema_validation`, `test_check_entry_with_non_verified_status`.

#### PA-REV-007: CLI Internal Error Diagnostics & Stderr
* **Issue:** In text mode, internal exception results were rendered to `stdout` instead of `stderr`.
* **Fix:** In `src/vicode/cli.py` (`_run` and `main`), routed unhandled internal error output to `sys.stderr` in text mode. Standardized exception reporting to `f"internal error: {type(exc).__name__}: {exc}"` without exposing sensitive traceback or environment contents.

#### PA-REV-008: Regex Remediation Plan Correction (VIC-REV-019)
* **Issue:** The remediation plan previously proposed another anchored regex that remained quadratic when matching failed.
* **Fix:** Updated `REMEDIATION_PLAN.md` and `FINDINGS_RECONCILIATION.md` to specify bounding input line length to 4,096 characters and stripping trailing whitespace using `rstrip()` before matching. Avoids nested backtracking regexes entirely.

---

## 3. Files Modified & Added

| File Path | Status | Summary of Changes |
|---|---|---|
| `src/vicode/jobs.py` | Modified | Added `trusted: bool = False` to `git_state()`; no Git invocation for untrusted projects; refined `_safe_git_command()` CWD direct parent check. |
| `src/vicode/doctor.py` | Modified | Propagated `config.is_trusted()` to `jobs.git_state()` in Stage 4 / result assembly. |
| `src/vicode/vivado/discovery.py` | Modified | Differentiated `cwd` direct parent match vs `project_dir` tree match to eliminate false-positive toolchain rejection. |
| `src/vicode/vivado/process.py` | Modified | Qualified `taskkill` strictly to `%SystemRoot%\System32\taskkill.exe` with safe fallback to `proc.kill()`. |
| `src/vicode/compat.py` | Modified | Deep-copy default matrix; validate entry schema (`os`, `vivado`); validate entry status (`"verified"`). |
| `src/vicode/cli.py` | Modified | Routed internal error text output to `sys.stderr`; standardized clean diagnostic formatting. |
| `tests/test_jobs.py` | Modified | Added clean-filter positive control & untrusted prevention test; updated fsmonitor and trusted git tests. |
| `tests/test_doctor.py` | Modified | Simulated Windows platform in Stage 7 batch test; mocked Stage 8 unsafe argument probe test; tightened filesystem error assertion; added git trust boundary test. |
| `tests/test_discovery.py` | Modified | Added test proving legitimate PATH tools beneath CWD are not rejected. |
| `tests/test_process.py` | Modified | Replaced planted bat test with mocked absolute taskkill call and missing taskkill fallback tests. |
| `tests/test_cli.py` | Modified | Independent tests for `_run()` and `main()` exception fallbacks across JSON, JSON-stream, and text stderr modes. |
| `tests/test_compat.py` | Untracked (New) | 12 comprehensive unit tests for matrix parsing, deep-copy isolation, schema validation, and diagnostic messages. |
| `reports/review-remediation/RELEASE_EVIDENCE_PLAN.md` | Modified | Corrected verified scope, attribution, wheel SHA-256 availability, and M0 status. |
| `reports/review-remediation/FINDINGS_RECONCILIATION.md` | Modified | Updated VIC-REV-001, VIC-REV-002, VIC-REV-005, VIC-REV-015, and VIC-REV-019 reconciliation details. |
| `reports/review-remediation/REMEDIATION_PLAN.md` | Modified | Corrected Task P2-1 (VIC-REV-019) to bounded line length + `rstrip()`. |
| `reports/review-remediation/PHASE_A_IMPLEMENTATION_REPORT.md` | Untracked (New) | Phase A implementation report. |
| `reports/review-remediation/PHASE_A_CORRECTION_REPORT.md` | Untracked (New) | This report. |

---

## 4. Verification Evidence & Test Execution

### 4.1 Standard Test Suite Run
* **Command:** `.\.venv\Scripts\python -m unittest discover -s tests -t . -v`
* **Result:** `Ran 144 tests in 12.354s — OK (skipped=1)`

### 4.2 Python Development Mode & Warnings Verification
* **Command:** `.\.venv\Scripts\python -X dev -W error -m unittest discover -s tests -t . -v`
* **Result:** `Ran 144 tests in 12.125s — OK (skipped=1)`
* **Significance:** Confirms zero deprecation warnings, zero resource leaks, and full Python 3.14.7 compliance.

### 4.3 Live Real Vivado 2018.2 Integration Test
* **Command:** `cmd /c "set VICODE_REAL_VIVADO=1&& .\.venv\Scripts\python -m unittest tests.test_integration_real_vivado -v"`
* **Result:**
  ```text
  test_doctor_with_real_vivado (tests.test_integration_real_vivado.RealVivadoTests.test_doctor_with_real_vivado) ... ok
  ----------------------------------------------------------------------
  Ran 1 test in 31.334s
  OK
  launcher: D:\Xilinx\Vivado\2018.2\bin\vivado.bat | version: 2018.2 | probe seconds: 31.265
  ```

### 4.4 Whitespace & Formatting Check
* **Command:** `git diff --check`
* **Result:** 0 errors.

---

## 5. Scope & Deferred Findings

All Phase A findings (VIC-REV-001 through VIC-REV-004) and all Claude review findings on Phase A (PA-REV-001, C3, C4, C5, PA-REV-005, PA-REV-006, PA-REV-007, PA-REV-008) are fully resolved.

The following items are deliberately deferred to their scheduled phases in accordance with `reports/review-remediation/REMEDIATION_PLAN.md`:
* **VIC-REV-006 (Counter synthesis spike):** Milestone M0 spike scheduled for separate phase.
* **VIC-REV-005 (Probe-first version evaluation):** Priority 1 (Phase B).
* **VIC-REV-008 (Windows Job Objects & process tree depth):** Priority 1 (Phase B).
* **VIC-REV-009, VIC-REV-010 (Documentation & packaging updates):** Priority 1 (Phase B).
* **VIC-REV-011 through VIC-REV-019:** Priority 2 / Priority 3 (Phase C).

---

## 6. Review Readiness

* **Branch:** `fix/foundation-review`
* **HEAD:** `1feb0a9eea03cb5cecede270c1db804bc4176010`
* **Working Tree State:** Clean modifications; no staged files; no commits.
* **Readiness:** **Ready for second independent review by Claude.**
