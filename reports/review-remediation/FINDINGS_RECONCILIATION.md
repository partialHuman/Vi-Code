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
3. **Reproduction on Windows:** Every technical finding was independently inspected and tested against the live Windows 11 runtime environment.

---

## 2. Findings Reconciliation Matrix (VIC-REV-001 through VIC-REV-019)

| Finding ID | Severity | Title / Area | Status | Needs Correction? |
|---|---|---|:---:|:---:|
| **VIC-REV-001** | High | Untrusted search path: current-directory `vivado.bat` / `git.exe` | **Confirmed & Reproduced** | **YES (P0)** |
| **VIC-REV-002** | Medium | Untrusted Git configuration execution (`core.fsmonitor`) | **Confirmed & Reproduced** | **YES (P0)** |
| **VIC-REV-003** | Medium | Recommended compatibility-matrix entry crashes `doctor` | **Confirmed & Reproduced** | **YES (P0)** |
| **VIC-REV-004** | Medium | Exceptions escape `doctor` as unstructured "internal error" | **Confirmed & Reproduced** | **YES (P0)** |
| **VIC-REV-005** | Medium | Compatibility evaluated before the probe from folder name | **Confirmed & Reproduced** | **YES (P1)** |
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
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:** `discovery.py` calls `shutil.which("vivado.bat")`. On Windows, `shutil.which` searches the current working directory first. A malicious `vivado.bat` in the project root is discovered via `PATH` with precedence over system installs. Similarly, bare `subprocess.run(["git", ...])` searches cwd for `git.exe`/`git.bat`.
* **Empirical Reproduction:**
  * Created test folder with mock `vivado.bat`.
  * Evaluated `shutil.which("vivado.bat")` under Python 3.14.7: returned `.\vivado.bat`.
  * Executed `vicode doctor --no-launch`: reported `found Vivado (unknown version) at .\vivado.bat via PATH`, prioritizing it over `D:\Xilinx\Vivado\2018.2\bin\vivado.bat`.
* **Impact:** Untrusted directory code execution when running `vicode doctor` inside an untrusted repository.
* **Correction Required:** Yes (P0). Discard `which` candidates matching cwd or project root unless explicitly configured; set `NoDefaultCurrentDirectoryInExePath=1` in `os.environ`; qualify `taskkill` with `%SystemRoot%\System32\taskkill.exe`; qualify `git` path outside cwd.

---

### VIC-REV-002: Untrusted Git Configuration Execution (`core.fsmonitor`)
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:** `jobs.git_state(path)` executes `git status --porcelain` in the project folder for any project with a valid manifest, regardless of trust. If `.git/config` sets `core.fsmonitor` to a payload script, Git executes it.
* **Empirical Reproduction:**
  * Initialized Git repo in project folder, committed files, and set `git config core.fsmonitor "<path>/payload.bat"`.
  * Executed `vicode doctor --no-launch`.
  * Verified `payload.bat` was executed by `git status --porcelain`, creating the marker file.
* **Impact:** Arbitrary code execution when running `doctor` on an untrusted cloned/downloaded repository.
* **Correction Required:** Yes (P0). Isolate git invocations with `-c core.fsmonitor=false -c core.useBuiltinFSMonitor=false --no-optional-locks`, set `GIT_CONFIG_NOSYSTEM=1`, and only invoke git state queries when appropriate.

---

### VIC-REV-003: Recommended Compatibility-Matrix Entry Crashes `doctor`
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:** `WINDOWS_READINESS_REPORT.md §6.1` and `TESTING_SUMMARY.md §5` recommended adding an entry formatted as a top-level JSON list `[...]`. The actual schema in `src/vicode/data/compat_matrix.json` is a JSON object with top-level key `"verified": [...]`. Loading a list causes `matrix.get("verified", [])` in `compat.py` to raise `AttributeError: 'list' object has no attribute 'get'`, crashing `doctor` without JSON output.
* **Empirical Reproduction:**
  * Tested list input against `compat.py`: raised `AttributeError: 'list' object has no attribute 'get'`.
  * Confirmed that `doctor --json` crashes with plain-text stderr, violating structured result guarantees.
* **Impact:** Following the delivered report's recommendation directly breaks `vicode doctor`.
* **Correction Required:** Yes (P0). Harden `compat.py` to validate matrix structure, degrade gracefully to "untested" with a warning diagnostic on schema mismatch, and format the verified entry in the proper object schema.

---

### VIC-REV-004: Unstructured Exception Escape in `doctor`
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:** `doctor.py` only catches `ProjectBusy`. Other exceptions (`UnsafeArgument`, `OSError`) escape to `cli.main` top-level handler, which outputs plain text `internal error: ...` to stderr without JSON formatting or `job.finished` event.
* **Empirical Reproduction:**
  * Created mock launcher at `$TEMP\Tools & Co\bin\vivado.bat` (containing `&`).
  * Executed `vicode doctor --vivado "$TEMP\Tools & Co\bin\vivado.bat" --json`.
  * Output: `internal error: argument '...' contains characters that are unsafe for a batch launcher (&)...` with exit code 1 and **zero JSON output**.
* **Impact:** Tool automation / GUI integrations fail to parse results on path validation errors or filesystem permissions issues.
* **Correction Required:** Yes (P0). Catch `UnsafeArgument` and expected `OSError` inside `run_doctor`, emit appropriate diagnostics in the structured result, and ensure top-level exception handler always outputs valid JSON when `--json` or `--json-stream` is requested.

---

### VIC-REV-005: Compatibility Evaluated Before Probe From Folder Name
* **Classification:** **Confirmed & Reproduced on Windows 11**.
* **Review Assertion:** Stage 7 in `doctor.py` checks compatibility using `selected.version` (derived from the folder name) before the probe runs in Stage 8. If the folder name does not match the actual binary version or is non-standard, the check uses wrong or null data and is never updated with the probed version.
* **Empirical Reproduction:**
  * Inspected `src/vicode/doctor.py:161-224`. Stage 7 executes `compat.check(version, plat)` at line 161. Stage 8 extracts `probed = markers.get("version")` at line 219, but never re-evaluates `compat.check`.
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
* **Correction Required:** No for 0.1.0 (Architecture §13 specifies path-based trust for 0.1; manifest content hashing is planned for 0.2).

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
* **Correction Required:** Yes (P2). Restructure regex to eliminate catastrophic backtracking, cap line length (e.g. 4,096 chars), and strip whitespace prior to matching.
