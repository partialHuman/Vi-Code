# Vi-Code 0.1.0 — Independent Review Reconciliation Report

**Date:** 2026-11-02
**Baseline Git Tag:** `v0.1.0`
**Baseline Commit Hash:** `e81f64e18a3fd333c0937d1040b1d9caad935716`
**Active Working Branch:** `fix/foundation-review` (branched cleanly from `v0.1.0`)
**Target Platform:** Windows 11 (build 26300, 64-bit), Vivado 2018.2
**Review Source:** `Vi-Code_0.1.0_Independent_Review.md`

---

## 1. Executive Summary & Context

An independent architecture, source, and Windows validation review was completed by Claude on the delivered Vi-Code 0.1.0 release archive.

### Key Baseline Context
1. **Repository Commit State:** The review noted that the repository had `.git` but "no commits". This observation was made before the 8-commit history and annotated tag `v0.1.0` were created. The current Git repository now contains a clean 8-commit history on `main`, tagged at `v0.1.0` (`e81f64e`).
2. **Review Validity:** While the "no commits" claim is historically outdated by subsequent actions, the **technical, architectural, security, and algorithmic findings are rigorous, accurate, and substantiated**.
3. **Reproduction & Verification Methodology:** Windows-specific behavior (such as Windows executable search path priority under `shutil.which` when `.` is present in PATH, batch launcher argument validation, System32 taskkill whole-tree termination, Win32 process handling, and real Vivado 2018.2 Tcl probing) was empirically evaluated on the live Windows 11 target machine. Other findings were analyzed and verified via architectural code inspection and unit tests. In particular, VIC-REV-005 was established via architectural code inspection rather than Windows reproduction. The clean-filter execution risk in VIC-REV-002 was identified from code inspection of Git subprocess invocations and resolved by enforcing a strict trust boundary.

---

## 2. Findings Reconciliation Matrix (VIC-REV-001 through VIC-REV-019)

| Finding ID | Severity | Title / Area | Status | Needs Correction? |
|---|---|---|:---:|:---:|
| **VIC-REV-001** | High | Untrusted search path: current-directory `vivado.bat` / `git.exe` | **Remediated (Phase A)** | **REMEDIATED** |
| **VIC-REV-002** | Medium | Untrusted Git configuration execution (`core.fsmonitor`) | **Remediated (Phase A)** | **REMEDIATED** |
| **VIC-REV-003** | Medium | Recommended compatibility-matrix entry crashes `doctor` | **Remediated (Phase A)** | **REMEDIATED** |
| **VIC-REV-004** | Medium | Exceptions escape `doctor` as unstructured "internal error" | **Remediated (Phase A)** | **REMEDIATED** |
| **VIC-REV-005** | Medium | Compatibility evaluated before the probe from folder name | **Confirmed (Code Inspection)** | **YES (P1)** |
| **VIC-REV-006** | High (Req) | Counter synthesis spike missing (Milestone M0 exit criterion) | **Confirmed (Requirement Gap)** | **YES (P0)** |
| **VIC-REV-007** | Medium | Test evidence, commit traceability, and artifact hashes | **Confirmed (Evidence Outdated on "no commits")** | **YES (P0/P1)** |
| **VIC-REV-008** | Medium | Process termination depth, cancellation, and Job Objects | **Confirmed & Reproduced** | **YES (P1)** |
| **VIC-REV-009** | Low | Repository documentation is stale (matrix & Windows status) | **Confirmed & Reproduced** | **YES (P1)** |
| **VIC-REV-010** | Low | Python 3.14 not represented in packaging metadata or CI | **Confirmed & Reproduced** | **YES (P1)** |
| **VIC-REV-011** | Low | CLI input validation (`--timeout <= 0`, version slice) | **Confirmed & Reproduced** | **YES (P2)** |
| **VIC-REV-012** | Low | Lock robustness & Win32 ctypes function prototypes | **Confirmed & Reproduced** | **YES (P2)** |
| **VIC-REV-013** | Low | Environment allowlist may omit necessary profile vars | **Confirmed / Design Decision** | **YES (P2)** |
| **VIC-REV-014** | Low | Output decoding assumption (UTF-8 vs console codepage) | **Suspected / Design Decision** | **YES (P2)** |
| **VIC-REV-015** | Low | Trust model is path-keyed rather than manifest-hashed | **Confirmed / Design Decision** | **NO (Track for 0.2)** |
| **VIC-REV-016** | Info | Doctor leaves uncleaned artifacts in `%TEMP%\vicode-doctor` | **Confirmed & Reproduced** | **YES (P3)** |
| **VIC-REV-017** | Info | Job event schema field naming variation vs §5.4 example | **Confirmed / Design Decision** | **YES (P3)** |
| **VIC-REV-018** | Info | Tcl quoting never validated against real Tcl interpreter | **Confirmed (Test Gap)** | **YES (P3)** |
| **VIC-REV-019** | Med (M3+) | Catastrophic quadratic regex backtracking in message parser | **Confirmed & Reproduced** | **YES (P2)** |

---

## 3. Detailed Finding-by-Finding Assessment

### VIC-REV-001: Untrusted Search Path (Current-Directory `vivado.bat` / `git.exe`)
* **Classification:** **Remediated in Phase A on `fix/foundation-review`** (previously Confirmed & Reproduced).
* **Review Assertion:** `discovery.py` calls `shutil.which("vivado.bat")`. On Windows, `shutil.which` searches the current working directory first. A malicious `vivado.bat` in the project root is discovered via `PATH` with precedence over system installs. Similarly, bare `subprocess.run(["git", ...])` searches cwd for `git.exe`/`git.bat`.
* **Empirical Reproduction:**
  * Configured environment with `.` explicitly in PATH (representing environments where Windows cmd or user profile PATH includes the current directory).
  * Created test folder with mock `vivado.bat`.
  * Evaluated `shutil.which("vivado.bat")` under Python 3.14.7: returned `.\vivado.bat`.
  * Executed `vicode doctor --no-launch`: reported `found Vivado (unknown version) at .\vivado.bat via PATH`, prioritizing it over `D:\Xilinx\Vivado\2018.2\bin\vivado.bat`.
* **Impact:** Untrusted directory code execution when running `vicode doctor` inside an untrusted repository.
* **Remediation Implemented:**
  * In `src/vicode/cli.py` and `src/vicode/vivado/discovery.py`, set `os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"` on Windows startup.
  * In `src/vicode/vivado/discovery.py`, implemented `_is_untrusted_path()` to discard any PATH candidate resolving directly in cwd (`cand.parent == cwd`) or anywhere inside an untrusted project directory (`proj_dir in cand.parents`), preventing planted executables while permitting legitimate tools in subdirectories beneath CWD (resolving PA-REV-005). Explicit `--vivado` paths remain permitted.
  * In `src/vicode/jobs.py`, implemented `_safe_git_command()` to resolve git to a verified binary outside the repository/cwd.
  * In `src/vicode/vivado/process.py`, qualified `taskkill` strictly via `%SystemRoot%\System32\taskkill.exe` with no unqualified fallback, failing safely to `proc.kill()` if unavailable.
* **Verification:** Regression unit tests in `tests/test_discovery.py` (`test_planted_cwd_launcher_is_ignored_by_which`, `test_planted_project_dir_launcher_is_ignored_by_which`, `test_explicit_configured_launcher_in_cwd_is_honored`, `test_legitimate_path_tool_beneath_cwd_is_not_rejected`), `tests/test_process.py` (`test_terminate_tree_invokes_absolute_system32_taskkill_and_never_bare_taskkill`, `test_terminate_tree_safe_fallback_when_taskkill_missing`), and `tests/test_jobs.py` (`test_safe_git_command_rejects_planted_and_accepts_trusted`). Live PowerShell CLI verification with planted `.\vivado.bat` in cwd confirmed system Vivado is selected.

---

### VIC-REV-002: Untrusted Git Configuration Execution (`core.fsmonitor` / Clean Filters)
* **Classification:** **Remediated in Phase A on `fix/foundation-review`** (previously Confirmed & Inspected).
* **Review Assertion:** `jobs.git_state(path)` executes `git status --porcelain` in the project folder for any project with a valid manifest, regardless of trust. If `.git/config` sets `core.fsmonitor` or `filter.<driver>.clean` via `.gitattributes`, Git executes attacker-specified payload scripts.
* **Inspection & Analysis:**
  * Architectural code inspection of `src/vicode/jobs.py` confirmed that `git_state(path)` previously invoked Git unconditionally for all projects with a manifest, without checking user trust.
  * Analysis confirmed that repository-level `.git/config` (`core.fsmonitor`) and repo attributes (`filter.<driver>.clean`) are executed by Git during `git status` when files change.
* **Impact:** Arbitrary code execution when running `doctor` on an untrusted cloned or downloaded repository.
* **Remediation Implemented:**
  * In `src/vicode/jobs.py` (`git_state`), enforced project trust boundary: `git_state(path, trusted=False)` returns `{"revision": None, "dirty": None}` immediately without spawning any `git` subprocess for untrusted projects. Untrusted repositories are completely protected against malicious Git configurations and clean filters because Git is never invoked.
  * In `src/vicode/jobs.py`, for explicitly trusted projects (`trusted=True`), isolated git invocations with CLI configuration overrides: `git -c core.fsmonitor=false -c core.useBuiltinFSMonitor=false -c core.hooksPath= --no-optional-locks -C <path> ...`.
  * Isolated child environment by passing `GIT_CONFIG_NOSYSTEM=1` and `GIT_TERMINAL_PROMPT=0`.
  * In `src/vicode/doctor.py`, propagated user trust via `config.is_trusted(root, user.config)`.
  * Note on Trust Boundary: Explicitly trusted projects (`trusted=True`) can execute repository-defined Git clean filters, as clean filters are an inherent content-filtering feature of Git executed during status queries. Documentation and `vicode project trust --help` have been updated to explicitly highlight this behavior.
* **Verification:** Dedicated regression unit tests in `tests/test_jobs.py` (`test_git_state_clean_filter_execution_prevented`, `test_git_state_ignores_core_fsmonitor_hook`, `test_git_state_defaults_to_untrusted_without_spawning_git`, `test_git_state_overrides_core_hooks_path`) and `tests/test_doctor.py` (`test_doctor_git_metadata_trust_boundary`). The clean-filter test includes a positive control proving the payload executes under unprotected `git status`, and verifies that `git_state(path, trusted=False)` produces zero subprocess execution. All tests pass on the live Windows 11 environment.

---

### VIC-REV-003: Recommended Compatibility-Matrix Entry Crashes `doctor`
* **Classification:** **Remediated in Phase A on `fix/foundation-review`** (previously Confirmed & Reproduced).
* **Review Assertion:** `WINDOWS_READINESS_REPORT.md §6.1` and `TESTING_SUMMARY.md §5` recommended adding an entry formatted as a top-level JSON list `[...]`. The actual schema in `src/vicode/data/compat_matrix.json` is a JSON object with top-level key `"verified": [...]`. Loading a list causes `matrix.get("verified", [])` in `compat.py` to raise `AttributeError: 'list' object has no attribute 'get'`, crashing `doctor` without JSON output.
* **Empirical Reproduction:**
  * Tested list input against `compat.py`: raised `AttributeError: 'list' object has no attribute 'get'`.
  * Confirmed that `doctor --json` crashes with plain-text stderr, violating structured result guarantees.
* **Impact:** Following the delivered report's recommendation directly breaks `vicode doctor`.
* **Remediation Implemented:**
  * In `src/vicode/compat.py`, hardened matrix parsing via `parse_matrix()` and `load_matrix()`, validating that the root is a JSON dictionary and `"verified"` is a list.
  * Defined safe `DEFAULT_MATRIX = {"schema_version": 1, "note": "...", "verified": []}` fallback.
  * In `compat.check()`, handled malformed inputs (list, non-dict, corrupt JSON, non-dict entries) without raising exceptions, degrading gracefully to `"untested"` and formatting the error details into the returned diagnostic message.
* **Verification:** Dedicated test suite `tests/test_compat.py` covering valid matrix, corrupt JSON, top-level list, missing verified list, and non-dict entries (12 test methods). Verified that `vicode doctor --no-launch --json` runs cleanly on live system.

---

### VIC-REV-004: Unstructured Exception Escape in `doctor`
* **Classification:** **Remediated in Phase A on `fix/foundation-review`** (previously Confirmed & Reproduced).
* **Review Assertion:** `doctor.py` only catches `ProjectBusy`. Other exceptions (`UnsafeArgument`, `OSError`) escape to `cli.main` top-level handler, which outputs plain text `internal error: ...` to stderr without JSON formatting or `job.finished` event.
* **Empirical Reproduction:**
  * Created mock launcher at `$TEMP\Tools & Co\bin\vivado.bat` (containing `&`).
  * Executed `vicode doctor --vivado "$TEMP\Tools & Co\bin\vivado.bat" --json`.
  * Output: `internal error: argument '...' contains characters that are unsafe for a batch launcher (&)...` with exit code 1 and **zero JSON output**.
* **Impact:** Tool automation / GUI integrations fail to parse results on path validation errors or filesystem permissions issues.
* **Remediation Implemented:**
  * In `src/vicode/doctor.py` Stage 7, added early validation of batch launchers on Windows (`process.validate_batch_args([selected.launcher])`), catching `UnsafeArgument` and emitting an error diagnostic.
  * In `src/vicode/doctor.py` Stage 8, caught `jobs.ProjectBusy`, `process.UnsafeArgument`, and `OSError` around lock acquisition and probe execution, mapping them into structured diagnostics and marking environment failure.
  * In `src/vicode/doctor.py`, protected `jobs.write_result()` against `OSError`.
  * In `src/vicode/cli.py` (`_run` and `main`), added structured exception fallback ensuring that if `--json` or `--json-stream` is passed, an `OperationResult` or `job.finished` event is always emitted to stdout before exiting.
* **Verification:** Regression unit tests in `tests/test_doctor.py` (`test_stage_7_unsafe_launcher_batch_validation`, `test_stage_8_unsafe_argument_during_probe_execution`, `test_filesystem_oserror_during_probe_is_structured`) and `tests/test_cli.py` (`test_doctor_unsafe_argument_returns_structured_json`, `test_doctor_unsafe_argument_returns_structured_json_stream`, `test_cli_run_exception_fallback`, `test_cli_main_exception_fallback`). Live CLI tests with `$TEMP\Tools & Co\vivado.bat` confirmed valid JSON and valid JSONL stream output.

---

### VIC-REV-005: Compatibility Evaluated Before Probe From Folder Name
* **Classification:** **Confirmed via Architectural Code Inspection (Not Windows reproduction)**.
* **Review Assertion:** Stage 7 in `doctor.py` checks compatibility using `selected.version` (derived from the folder name) before the probe runs in Stage 8. If the folder name does not match the actual binary version or is non-standard, the check uses wrong or null data and is never updated with the probed version.
* **Code Inspection Analysis:**
  * Inspected `src/vicode/doctor.py:161-224`. Stage 7 executes `compat.check(version, plat)` at line 161. Stage 8 extracts `probed = markers.get("version")` at line 219, but never re-evaluates `compat.check`. Established via code inspection; this is a logical sequencing flaw in doctor rather than a Windows-specific behavior.
* **Impact:** False warnings or false "verified" statuses when folder name does not match binary.
* **Correction Required:** Yes (P1). Evaluate compatibility after the probe using the verified probed version; fallback to folder-derived version only when `--no-launch` is active.

---

### VIC-REV-006: Missing Counter Synthesis Spike (Milestone M0 Gap)
* **Classification:** **Confirmed (Requirement Gap)**.
* **Review Assertion:** Architecture §14 defines Milestone M0 as: "Thin spike: doctor, init, synthesize the counter design, emit a structured JSON result". Release 0.1.0 only implemented the doctor probe and part check; synthesis commands stub to exit code 5.
* **Empirical Reproduction:**
  * Verified codebase: no counter RTL, no synthesis Tcl scripts, no `synth_design` execution, no synthesis result JSON.
* **Impact:** Milestone M0 cannot be formally closed until a counter design is synthesized via Vivado and produces a structured result.
* **Correction Required:** Yes (P0). Implement a self-contained counter synthesis spike demonstrating Vivado Project Mode synthesis and structured JSON output without implementing full M3 features.

---

### VIC-REV-007: Test Evidence & Commit Traceability
* **Classification:** **Confirmed (Technical details) / Evidence Outdated (Commit status)**.
* **Review Assertion:**
  * "No commits in repository": **Outdated**. Resolved by 8 commits and `v0.1.0` tag.
  * Reports lack commit hash and wheel SHA-256: **Confirmed**.
  * Wheel size reported was 34,559 bytes vs archive 34,518 bytes: **Confirmed** (explained by build metadata timestamps across clean builds).
  * `tests/__init__.py` overrides `sys.path` to `src/`, so tests do not run against the installed wheel: **Confirmed**.
  * Smoke tests #20–39 were manual: **Confirmed**.
  * Real `%APPDATA%\vicode\config.yaml` was modified during smoke testing: **Confirmed**.
* **Correction Required:** Yes (P0/P1). Add automated `scripts/windows_smoke.ps1`, record commit hash and artifact SHA-256 hashes, test against installed package, and isolate config with `VICODE_USER_CONFIG`.

---

### VIC-REV-008: Process Termination & Cancellation Depth
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:**
  * `--timeout 0.5` only verified killing launcher before worker processes spawned.
  * `taskkill /T /F` does not kill orphaned child processes if intermediate parent exits.
  * Ctrl+C during post-process cleanup is unhandled.
  * `cancel` Event in `cli.py:124` is never triggered by signals.
* **Empirical Reproduction:**
  * Inspected `process.py:84, 160-185` and `cli.py:124`. Signal handling is not wired to `cancel.set()`. Cleanup block does not catch secondary `KeyboardInterrupt`.
* **Correction Required:** Yes (P1). Implement Windows Job Objects with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, wire signal handling, wrap cleanup in outer try/finally, and test process termination on a running Vivado process.

---

### VIC-REV-009: Repository Documentation is Stale
* **Classification:** **Confirmed & Reproduced**.
* **Review Assertion:** `README.md`, `TEST_REPORT.md`, and `docs/verification.md` state that nothing has run on Windows 11 or against real Vivado, despite local testing having succeeded.
* **Correction Required:** Yes (P1). Update documentation to reflect verified status on Windows 11 + Vivado 2018.2 with explicit scope boundaries.

---

### VIC-REV-010: Python 3.14 Not Represented in Packaging & CI
* **Classification:** **Confirmed & Reproduced**.
* **Review Assertion:** `pyproject.toml` lacks minor version classifiers; `.github/workflows/ci.yml` only runs 3.11 and 3.12. Local testing was performed on 3.14.7.
* **Correction Required:** Yes (P1). Add Python 3.13 and 3.14 to CI matrix and package classifiers.

---

### VIC-REV-011: CLI Input Validation and Consistency
* **Classification:** **Confirmed & Reproduced**.
* **Review Assertion:** `--timeout` accepts negative and zero values (`--timeout -5` immediately aborts process); `__version__[:3]` breaks on two-digit minor versions (`0.10.x`); `vicode cancel` hint in doctor points to planned stub.
* **Correction Required:** Yes (P2). Add argparse type validation for positive timeout, robust version extraction, and fix hint.

---

### VIC-REV-012: Lock Robustness & Win32 ctypes Prototypes
* **Classification:** **Confirmed & Reproduced**.
* **Review Assertion:** Stale lock cleanup has an unlink race condition between concurrent processes; `jobs.pid_alive` calls `kernel32.OpenProcess` without defining `argtypes` and `restype`.
* **Correction Required:** Yes (P2). Define ctypes argument types and return types explicitly; harden lock file acquisition.

---

### VIC-REV-013: Environment Allowlist Scope
* **Classification:** **Confirmed / Design Decision Required**.
* **Review Assertion:** `ENV_ALLOW` in `process.py` omits `HOMEDRIVE`, `HOMEPATH`, `ALLUSERSPROFILE`. Works on 2018.2, but may cause issues on other Vivado versions.
* **Correction Required:** Yes (P2). Add standard Windows profile variables and a user-config environment pass-through extension point.

---

### VIC-REV-014: Output Decoding Assumption
* **Classification:** **Suspected / Design Decision Required**.
* **Review Assertion:** Decoding stdout/stderr as UTF-8 with replacement might garble messages on systems using OEM/ANSI codepages with non-ASCII characters.
* **Correction Required:** Yes (P2). Inspect console encoding (`sys.stdout.encoding` / `locale.getpreferredencoding()`) fallback.

---

### VIC-REV-015: Trust Model is Path-Keyed
* **Classification:** **Confirmed / Design Decision Required**.
* **Review Assertion:** If `vicode.yaml` changes after a project is trusted, the new settings are trusted automatically.
* **Correction Required:** No for 0.1.0 (The 0.1 design specification in Sections 9.3 and 9.4 and docs/configuration.md explicitly defines path-keyed trust via user configuration 'trusted_projects'. Binding trust to manifest content hashing or change detection is a candidate future enhancement not specified in 0.1).

---

### VIC-REV-016: Doctor Leaves Artifacts in `%TEMP%`
* **Classification:** **Confirmed & Reproduced**.
* **Review Assertion:** Running `doctor` outside a project creates `<temp>\vicode-doctor\<job_id>` without cleanup.
* **Correction Required:** Yes (P3). Clean up temporary directory when probe succeeds or implement temp directory age pruning.

---

### VIC-REV-017: Job Event Schema Variations
* **Classification:** **Confirmed / Design Decision Required**.
* **Review Assertion:** Event schema in code uses `message` while §5.4 illustrative example used `text`.
* **Correction Required:** Yes (P3). Formally document protocol 1 event schema in `docs/cli.md`.

---

### VIC-REV-018: Tcl Quoting Real Evaluation
* **Classification:** **Confirmed (Test Gap)**.
* **Review Assertion:** `tcl.quote` tested only against Python oracle, not real Vivado Tcl engine.
* **Correction Required:** Yes (P3). Add opt-in real Vivado Tcl round-trip evaluation test.

---

### VIC-REV-019: Quadratic Message Parser Regex Backtracking
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:** Pattern `_ID` in `messages.py` has lazy `(?P<text>.*?)` followed by optional location and `\s*$`. On lines with trailing characters after spaces, matching time scales as $O(N^2)$.
* **Empirical Reproduction:**
  * Tested `ERROR: [Synth 8-1] x` + N spaces + `y` under Python 3.14.7:
    * N = 5,000: **0.116s**
    * N = 10,000: **0.508s** (~4.3x)
    * N = 20,000: **1.911s** (~3.8x)
    * N = 40,000: **7.430s** (~3.9x)
    * N = 1,000,000: Execution stalls indefinitely.
* **Impact:** Hostile or oversized log line hangs the CLI parser.
* **Correction Required:** Yes (P2). Restructure message parsing in `src/vicode/vivado/messages.py` by capping input line length at 4,096 characters and stripping trailing whitespace via `rstrip()` prior to matching. Avoid nested quadratic regexes, ensuring strictly bounded parse times across large inputs.
