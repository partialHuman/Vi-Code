# Vi-Code 0.1.0 — Remediation & Hardening Plan

**Date:** 2026-11-02
**Target Branch:** `fix/foundation-review`
**Baseline:** `v0.1.0` (`e81f64e18a3fd333c0937d1040b1d9caad935716`)
**Scope:** Remediation of findings VIC-REV-001 through VIC-REV-019

---

## 1. Prioritized Remediation Tasks

### Priority 0 — Security, Crash & Milestone Blockers

#### Task P0-1: Secure Windows Executable Search Paths (VIC-REV-001)
* **Objective:** Prevent execution of malicious current-directory `vivado.bat` or `git.exe`.
* **Changes:**
  * In `src/vicode/cli.py` on Windows startup, set `os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"`.
  * In `src/vicode/vivado/discovery.py`, discard any `which()` result where `os.path.dirname(os.path.abspath(hit))` matches `cwd` or `project_dir` unless explicitly passed via `--vivado`.
  * In `src/vicode/jobs.py` (`git_state`), resolve `git` explicitly using system path or absolute `shutil.which` outside the repository folder.
  * In `src/vicode/vivado/process.py`, resolve `taskkill` via `%SystemRoot%\System32\taskkill.exe`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * A planted `vivado.bat` in cwd is ignored when running `vicode doctor`.
  * System Vivado is selected; if no system Vivado exists, reports `no Vivado installation found` (exit 3).
* **Regression Tests:** Windows test planting a dummy `vivado.bat` in cwd and asserting it is skipped by `discovery.discover`.

---

#### Task P0-2: Isolate Git State Execution Against Malicious Configs (VIC-REV-002)
* **Objective:** Prevent repository-controlled `.git/config` from executing arbitrary scripts via `core.fsmonitor` during `doctor`.
* **Changes:**
  * In `src/vicode/jobs.py` (`git_state`), run git with configuration overrides:
    ```python
    ["git", "-c", "core.fsmonitor=false", "-c", "core.useBuiltinFSMonitor=false", "--no-optional-locks", "-C", str(path), *args]
    ```
  * In child environment, pass `GIT_CONFIG_NOSYSTEM=1`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * `vicode doctor --no-launch` inside a repository with `core.fsmonitor = <malicious_script>` executes git safely without triggering the monitor script.
  * Clean repository still correctly reports revision and dirty status.
* **Regression Tests:** Unit test setting `core.fsmonitor` to a script creating a marker file; asserting marker file is never created.

---

#### Task P0-3: Harden Compatibility Matrix Schema & Error Recovery (VIC-REV-003)
* **Objective:** Ensure malformed compatibility matrix files cannot crash `doctor` or break `--json` output.
* **Changes:**
  * In `src/vicode/compat.py`, validate matrix root is a dictionary and contains list `"verified"`.
  * On JSON decode error or invalid schema, log a warning diagnostic, degrade gracefully to status `"untested"`, and never raise an uncaught exception.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * If `compat_matrix.json` is a list, empty file, or corrupt JSON, `doctor --json` returns exit code 0 (or 2/3 as appropriate) with valid JSON and diagnostic warning.
* **Regression Tests:** Test cases in `test_config.py` loading invalid matrix shapes (list, string, corrupted JSON).

---

#### Task P0-4: Structure All Exception Handling in CLI & Doctor (VIC-REV-004)
* **Objective:** Prevent unhandled exceptions from escaping as raw stderr strings without structured JSON.
* **Changes:**
  * In `src/vicode/doctor.py`, catch `UnsafeArgument` and filesystem `OSError` around lock acquisition and probe execution, mapping them into `Diagnostic("error", ...)` and `state["env_failed"] = True` or `state["config_failed"] = True`.
  * In `src/vicode/cli.py` (`main`), ensure that in the event of an unexpected exception, if `--json` or `--json-stream` was passed, an `OperationResult` JSON object or `job.finished` event is emitted before exiting with code 1.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * `vicode doctor --vivado "C:\Path & Co\vivado.bat" --json` returns valid JSON with `exit_code: 1` and diagnostic describing the disallowed character.
* **Regression Tests:** CLI test passing a launcher with `&` in the path with `--json` asserting valid parseable JSON output.

---

#### Task P0-5: Implement M0 Counter Synthesis Spike (VIC-REV-006)
* **Objective:** Deliver the required Milestone M0 synthesis proof-of-concept without prematurely implementing full M3 features.
* **Changes:**
  * Create a standalone spike module or script (`scripts/m0_counter_spike.py` / `src/vicode/vivado/spike.py`).
  * Include minimal synthesizable counter RTL (`rtl/counter.v`).
  * Generate and execute a Vivado Project Mode Tcl synthesis script.
  * Emit a protocol 1 structured JSON result recording synthesis success/failure, tool version, duration, logs, and utilization report.
* **Dependencies:** P0-3, P0-4.
* **Acceptance Criteria:**
  * Real Vivado 2018.2 executes synthesis on Windows 11 and produces a gate netlist and utilization report.
  * Structured JSON result emitted with status `succeeded`.
  * RTL syntax error test emits status `failed` with exit code 1 and error diagnostics.
* **Regression Tests:** Fake-Vivado contract test and opt-in real Vivado test (`test_integration_real_vivado.py`).

---

#### Task P0-6: Establish Commit Traceability & Release Hashes (VIC-REV-007)
* **Objective:** Bind all verification evidence directly to verified Git commit hashes and artifact SHA-256 checksums.
* **Changes:**
  * Record exact commit hash in test reports.
  * Compute and record SHA-256 for release wheels and source archives.
  * Ensure reports explain the build metadata timestamp difference between clean builds.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * All documentation and reports cite verifiable commit hashes and SHA-256 hashes.

---

### Priority 1 — Production & Release Readiness

#### Task P1-1: Post-Probe Compatibility Evaluation (VIC-REV-005)
* **Objective:** Evaluate tool compatibility using the probed version rather than path heuristics.
* **Changes:**
  * In `src/vicode/doctor.py`, re-evaluate `compat.check` after Stage 8 probe when `probed` is available.
  * If probe was skipped (`--no-launch`), annotate compatibility message as folder-derived.
* **Dependencies:** P0-3.
* **Acceptance Criteria:**
  * A Vivado install in a folder named `2023.2` that reports version `2018.2` receives the compatibility verdict for `2018.2`.
* **Regression Tests:** Mock test where folder version differs from probed version.

---

#### Task P1-2: Robust Process Termination with Windows Job Objects (VIC-REV-008)
* **Objective:** Ensure clean termination of all child processes (including grandchild workers) even if launcher exits.
* **Changes:**
  * In `src/vicode/vivado/process.py`, create a Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and assign child processes to it.
  * Wrap cleanup in outer `try/finally` so repeated `KeyboardInterrupt` does not bypass cleanup.
  * Connect signal handlers to set `cancel` Event in `cli.py`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * Cancelling or timing out a running Vivado batch job terminates all sub-processes (`vivado.bat`, `vvgl`, Java workers).
* **Regression Tests:** Process tree termination test with long-running subprocess tree.

---

#### Task P1-3: Refresh Documentation & Compatibility Matrix (VIC-REV-009)
* **Objective:** Update documentation to reflect verified Windows 11 + Vivado 2018.2 status.
* **Changes:**
  * Update `README.md`, `CHANGELOG.md`, `TEST_REPORT.md`, `docs/verification.md`.
  * Update `src/vicode/data/compat_matrix.json` with properly formatted object entry.
* **Dependencies:** P0-3, P0-5.
* **Acceptance Criteria:**
  * `vicode doctor` on Windows 11 + Vivado 2018.2 reports `[ OK ] compatibility: verified`.

---

#### Task P1-4: Update Python Metadata and CI Matrix (VIC-REV-010)
* **Objective:** Formally declare and verify Python 3.13 and 3.14 support.
* **Changes:**
  * In `pyproject.toml`, add classifiers for Python 3.11, 3.12, 3.13, 3.14.
  * In `.github/workflows/ci.yml`, include Python 3.13 and 3.14 in test matrix and add `-X dev -W error`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * CI passes across all declared Python versions.

---

#### Task P1-5: Strengthen Real-Vivado Automated Integration Tests (VIC-REV-008, VIC-REV-007)
* **Objective:** Make real Vivado test assertions comprehensive and repeatable.
* **Changes:**
  * In `tests/test_integration_real_vivado.py`, assert probe markers, valid part detection, invalid part rejection, timeout handling, and log generation.
* **Dependencies:** P0-1, P0-5.
* **Acceptance Criteria:**
  * `python -m unittest tests.test_integration_real_vivado -v` asserts comprehensive functional behavior.

---

#### Task P1-6: Automated Scripted Windows Smoke Test (VIC-REV-007)
* **Objective:** Provide a single-command repeatable script replicating all CLI smoke tests.
* **Changes:**
  * Create `scripts/windows_smoke.ps1` running scenarios #1 through #39.
  * Set `VICODE_USER_CONFIG` to a temporary directory to isolate test trust operations from `%APPDATA%`.
* **Dependencies:** P0-1, P0-4.
* **Acceptance Criteria:**
  * Running `.\scripts\windows_smoke.ps1` executes all CLI tests cleanly and reports 100% pass without modifying real user config.

---

### Priority 2 — Code Quality & Hardening

#### Task P2-1: Fix Quadratic Message Parser Backtracking (VIC-REV-019)
* **Objective:** Eliminate catastrophic backtracking in `messages.py`.
* **Changes:**
  * In `src/vicode/vivado/messages.py`, cap line length at 4,096 chars and `rstrip()` before regex matching.
  * Re-anchor regex pattern `_ID` to prevent backtracking across trailing whitespace:
    ```python
    _ID = re.compile(
        r"^(?P<sev>INFO|WARNING|CRITICAL WARNING|ERROR):\s+"
        r"\[(?P<cat>[A-Za-z][A-Za-z0-9]*)\s+(?P<num>[A-Za-z0-9]+-\d+)\]\s*"
        r"(?P<text>.*?)(?:\s+\[(?P<file>[^\[\]]+?):(?P<line>\d+)\])?$"
    )
    ```
* **Dependencies:** None.
* **Acceptance Criteria:**
  * A 1 MB line with 50,000 trailing spaces parses in < 0.01 seconds.
  * All existing message parsing test cases continue to pass identically.
* **Regression Tests:** Unit test with 100,000-character whitespace line asserting parse duration < 0.05s.

---

#### Task P2-2: CLI Input Validation Hardening (VIC-REV-011)
* **Objective:** Enforce positive float bounds on `--timeout` and robust version string extraction.
* **Changes:**
  * Add custom argparse float validator requiring `timeout > 0`.
  * Fix version string parsing using `packaging.version` or `version.split('.')[:2]`.
  * Correct doctor hint to avoid pointing to unavailable `vicode cancel`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * `vicode doctor --timeout -1` or `--timeout 0` returns exit code 2 with usage error.

---

#### Task P2-3: Win32 ctypes Function Signatures & Lock Hardening (VIC-REV-012)
* **Objective:** Eliminate 64-bit handle truncation risk and race conditions in lock unlinking.
* **Changes:**
  * Explicitly specify `kernel32.OpenProcess.argtypes` and `kernel32.OpenProcess.restype = wintypes.HANDLE`.
  * Specify `kernel32.GetExitCodeProcess.argtypes` and `restype = wintypes.BOOL`.
  * Include process start time in lock acquisition verification.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * Win32 ctypes calls adhere strictly to Windows SDK function signatures.

---

#### Task P2-4: Expand Process Environment Allowlist (VIC-REV-013)
* **Objective:** Ensure Vivado and Tcl find necessary user profile directories on Windows.
* **Changes:**
  * Add `HOMEDRIVE`, `HOMEPATH`, `ALLUSERSPROFILE`, `OS`, `SYSTEMINFO` to `ENV_ALLOW`.
  * Add user configuration extension `extra_environment_variables` in `config.yaml`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * Expanded environment variables pass through to child processes when present.

---

#### Task P2-5: Output Decoding Codepage Fallback (VIC-REV-014)
* **Objective:** Prevent mojibake/garbled text when Vivado emits OEM/ANSI console codepages.
* **Changes:**
  * In `process.py`, determine process encoding using `sys.stdout.encoding` or `locale.getpreferredencoding(False)`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  * Non-ASCII paths and message characters decode cleanly without raising decode errors.

---

### Priority 3 — Minor Hygiene & Schema Freezing

#### Task P3-1: Doctor Temp Directory Cleanup (VIC-REV-016)
* Clean up `<temp>\vicode-doctor\<job_id>` when doctor completes successfully outside a project.

#### Task P3-2: Formalize Protocol 1 Event Schema (VIC-REV-017)
* Freeze and document event schema fields (`message` vs `text`, result object embedding) in `docs/cli.md`.

#### Task P3-3: Real Vivado Tcl Quoting Round-Trip Test (VIC-REV-018)
* Add an opt-in test executing dynamic strings through real Vivado Tcl to verify escaping of spaces, braces, and non-ASCII chars.

---

## 2. Recommended Implementation Sequence

```mermaid
flowchart TD
    subgraph Phase A: Security & Crash Hardening
        P0-1["P0-1: Secure Windows Search Paths"]
        P0-2["P0-2: Isolate Git State Execution"]
        P0-3["P0-3: Harden Compat Matrix Schema"]
        P0-4["P0-4: Structure Exception Handling"]
    end

    subgraph Phase B: Reliability & Performance
        P1-1["P1-1: Post-Probe Compat Evaluation"]
        P2-1["P2-1: Fix Quadratic Regex Parser"]
        P2-2["P2-2: CLI Input Validation"]
        P2-3["P2-3: Win32 ctypes Prototypes"]
        P2-4["P2-4: Expand Environment Allowlist"]
    end

    subgraph Phase C: Process & Job Objects
        P1-2["P1-2: Windows Job Object Termination"]
    end

    subgraph Phase D: Milestone M0 Synthesis Spike
        P0-5["P0-5: Counter Synthesis Spike"]
    end

    subgraph Phase E: Test Automation & CI
        P1-5["P1-5: Strengthen Real-Vivado Tests"]
        P1-6["P1-6: Scripted Windows Smoke Test"]
        P1-4["P1-4: Python 3.14 CI Matrix"]
        P3-3["P3-3: Real Tcl Quoting Test"]
    end

    subgraph Phase F: Release Documentation & Evidence
        P1-3["P1-3: Refresh Docs & Compat Matrix"]
        P0-6["P0-6: Commit Traceability & Hashes"]
        P3-1["P3-1: Doctor Temp Cleanup"]
        P3-2["P3-2: Freeze Event Schema"]
    end

    Phase A --> Phase B
    Phase B --> Phase C
    Phase C --> Phase D
    Phase D --> Phase E
    Phase E --> Phase F
```
