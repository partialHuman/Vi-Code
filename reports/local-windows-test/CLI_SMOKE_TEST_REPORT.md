# Vi-Code 0.1.0 — CLI Smoke Test Report

**Date:** 2026-11-01<br>
**Project:** Vi-Code 0.1.0<br>
**Test Host:** Windows 11 (build 26300, 64-bit)<br>
**Binary Tested:** `.\.venv\Scripts\vicode.exe` (entry point defined in `pyproject.toml`)<br>
**Secondary Clean Environment:** `.\clean_venv\Scripts\vicode.exe` (installed from built `.whl`)<br>

---

## 1. Summary Matrix

| # | Command / Action | Test Category | Expected Exit Code | Actual Exit Code | Result |
|---|---|---|:---:|:---:|:---:|
| 1 | `vicode --version` | Version Check | 0 | 0 | **PASS** |
| 2 | `vicode --help` | Global Help | 0 | 0 | **PASS** |
| 3 | `vicode doctor --help` | Subcommand Help | 0 | 0 | **PASS** |
| 4 | `vicode init --help` | Subcommand Help | 0 | 0 | **PASS** |
| 5 | `vicode project --help` | Subcommand Help | 0 | 0 | **PASS** |
| 6 | `vicode` (no arguments) | CLI Usage Validation | 2 | 2 | **PASS** |
| 7 | `vicode nonexistent` | Argument Parsing | 2 | 2 | **PASS** |
| 8 | `vicode project` (no action) | Incomplete Subcommand | 2 | 2 | **PASS** |
| 9 | `vicode synth` | Planned Feature Stub | 5 | 5 | **PASS** |
| 10 | `vicode sim` | Planned Feature Stub | 5 | 5 | **PASS** |
| 11 | `vicode init myproj` | Project Workspace Creation | 0 | 0 | **PASS** |
| 12 | `vicode init optproj --part ... --board ...` | Init with Custom Options | 0 | 0 | **PASS** |
| 13 | `vicode init "space proj" --dir ...` | Identifier Name Validation | 2 | 2 | **PASS** |
| 14 | `vicode init space_proj --dir "path with spaces\space_proj"` | Target Directory with Spaces | 0 | 0 | **PASS** |
| 15 | `vicode init jsonproj --json` | Init JSON Structured Output | 0 | 0 | **PASS** |
| 16 | `vicode init myproj` (already exists) | Guard Against Overwriting | 1 | 1 | **PASS** |
| 17 | `vicode init "bad/name"` | Guard Against Invalid Name | 2 | 2 | **PASS** |
| 18 | `vicode project validate` (inside `myproj`) | Valid Manifest Validation | 0 | 0 | **PASS** |
| 19 | `vicode project validate --json` | Validation JSON Output | 0 | 0 | **PASS** |
| 20 | `vicode project validate` (in directory with spaces) | Spaces in Project Path | 0 | 0 | **PASS** |
| 21 | `vicode project validate` (outside project) | Missing Manifest Error | 2 | 2 | **PASS** |
| 22 | `vicode project validate` (unknown key in YAML) | Strict Schema Enforcement | 2 | 2 | **PASS** |
| 23 | `vicode project validate` (duplicate YAML key) | Safe YAML Parser Rules | 2 | 2 | **PASS** |
| 24 | `vicode project validate` (invalid schema_version) | Schema Version Check | 2 | 2 | **PASS** |
| 25 | `vicode project trust` (inside `myproj`) | Project Trust Recording | 0 | 0 | **PASS** |
| 26 | `vicode project trust --json` | Trust JSON Output | 0 | 0 | **PASS** |
| 27 | `vicode project trust` (in path with spaces) | Spaces in Project Path | 0 | 0 | **PASS** |
| 28 | `vicode project trust` (outside project) | Missing Project Error | 2 | 2 | **PASS** |
| 29 | `vicode doctor --no-launch` (inside project) | Fast Doctor Check | 0 | 0 | **PASS** |
| 30 | `vicode doctor --no-launch --json` | Doctor JSON Output | 0 | 0 | **PASS** |
| 31 | `vicode doctor --no-launch --json-stream` | Doctor JSONL Event Stream | 0 | 0 | **PASS** |
| 32 | `vicode doctor --no-launch` (outside project) | Doctor Without Project | 0 | 0 | **PASS** |
| 33 | `vicode doctor --vivado C:\NonExistent\... --no-launch` | Missing Vivado Detection | 3 | 3 | **PASS** |
| 34 | `vicode doctor` (invalid config + invalid vivado) | Config Error Precedence | 2 | 2 | **PASS** |
| 35 | `vicode doctor` (real Vivado batch probe) | Real Vivado Execution | 0 | 0 | **PASS** |
| 36 | `vicode doctor` (target part valid) | Real Part Verification | 0 | 0 | **PASS** |
| 37 | `vicode doctor` (target part invalid) | Real Part Missing Detection | 3 | 3 | **PASS** |
| 38 | `vicode doctor` (in path with spaces) | Space Handling with Real Tool | 0 | 0 | **PASS** |
| 39 | `vicode doctor --timeout 0.5` | Process Timeout & Taskkill | 3 | 3 | **PASS** |

---

## 2. Detailed Test Evidence

### 2.1 Basic CLI Options & Planned Stubs
* **Command:** `vicode --version`
  * **Expected Output:** `vicode 0.1.0`
  * **Actual Output:** `vicode 0.1.0`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode synth`
  * **Expected Output:** Planned command diagnostic stating availability in 0.3
  * **Actual Output:** `ERROR: 'vicode synth' is planned for release 0.3 and is not available in release 0.1`
  * **Exit Code:** `5` (PASS)
* **Command:** `vicode nonexistent`
  * **Expected Output:** Argument error listing valid subcommands
  * **Actual Output:** `vicode: error: argument <command>: invalid choice: 'nonexistent'`
  * **Exit Code:** `2` (PASS)

### 2.2 `vicode init`
* **Command:** `vicode init myproj`
  * **Expected Output:** Project scaffold created (`vicode.yaml`, `.gitignore`, `README.md`, `rtl`, `sim`, `constraints`, `ip`, `scripts`)
  * **Actual Output:** `init: created C:\...\myproj - next: cd into it and run 'vicode doctor'  (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode init "space proj" --dir "path with spaces\space proj"`
  * **Expected Output:** Rejection because the project name itself contains whitespace
  * **Actual Output:** `ERROR: project.name: 'space proj' is not a valid project name (letters, digits, '_' and '-', starting with a letter)`
  * **Exit Code:** `2` (PASS)
* **Command:** `vicode init space_proj --dir "path with spaces\space_proj"`
  * **Expected Output:** Project scaffold created in directory with spaces
  * **Actual Output:** `init: created path with spaces\space_proj - next: cd into it and run 'vicode doctor'  (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode init myproj` (when already existing)
  * **Expected Output:** Refusal to overwrite non-empty folder
  * **Actual Output:** `ERROR: C:\...\myproj already exists and is not an empty directory; init: could not create the project  (exit 1)`
  * **Exit Code:** `1` (PASS)

### 2.3 `vicode project validate`
* **Command:** `vicode project validate` (inside `myproj`)
  * **Expected Output:** Manifest is valid
  * **Actual Output:** `project.validate: C:\...\myproj\vicode.yaml is valid  (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode project validate` (in directory with spaces)
  * **Expected Output:** Manifest is valid
  * **Actual Output:** `project.validate: C:\...\path with spaces\space_proj\vicode.yaml is valid  (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode project validate` (outside project)
  * **Expected Output:** Error indicating no `vicode.yaml`
  * **Actual Output:** `ERROR: no vicode.yaml found; hint: Run 'vicode init' or use --project-dir; project.validate: no vicode.yaml found  (exit 2)`
  * **Exit Code:** `2` (PASS)
* **Command:** `vicode project validate --project-dir <inv1>` (unknown key)
  * **Expected Output:** Schema error
  * **Actual Output:** `ERROR: unknown_setting: unknown key; project.validate: 1 problem(s) in ...\inv1\vicode.yaml  (exit 2)`
  * **Exit Code:** `2` (PASS)
* **Command:** `vicode project validate --project-dir <inv2>` (duplicate key)
  * **Expected Output:** YAML parser duplicate key error
  * **Actual Output:** `ERROR: <file>: YAML error: duplicate key 'project'; project.validate: 1 problem(s) in ...\inv2\vicode.yaml  (exit 2)`
  * **Exit Code:** `2` (PASS)

### 2.4 `vicode project trust`
* **Command:** `vicode project trust`
  * **Expected Output:** Trust recorded in user configuration
  * **Actual Output:** `project.trust: trusted C:\...\myproj (recorded in C:\Users\User\AppData\Roaming\vicode\config.yaml)  (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Inspection of `config.yaml`:**
  ```yaml
  schema_version: 1
  trusted_projects:
  - C:\Users\User\AppData\Local\Temp\vicode_cli_test_36d9db81\myproj
  - C:\Users\User\AppData\Local\Temp\vicode_cli_test_36d9db81\path with spaces\space_proj
  ```
  *Properly saved and formatted.*

### 2.5 `vicode doctor` (Environment & Vivado Checks)
* **Command:** `vicode doctor --no-launch`
  * **Expected Output:** Checks 1-7 succeed, probe skipped, exit code 0
  * **Actual Output:**
    ```text
    [ OK ] python: Python 3.14.7
    [ OK ] platform: Windows 11 (build 26300)
    [ OK ] user_config: loaded C:\Users\User\AppData\Roaming\vicode\config.yaml
    [ OK ] project_config: C:\...\myproj\vicode.yaml is valid (project 'myproj')
    [ OK ] vivado_discovery: found Vivado 2018.2 at D:\Xilinx\Vivado\2018.2\bin\vivado.bat via default-root
    [ OK ] vivado_launcher: launcher exists and is executable
    [WARN] compatibility: windows-11 + Vivado 2018.2 is not in the verified compatibility matrix yet (see docs/verification.md to record a verified combination)
    [SKIP] vivado_probe: skipped (--no-launch): Vivado was not started
    doctor: environment is ready (1 warning)  (exit 0)
    ```
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode doctor --vivado C:\NonExistent\bin\vivado.bat --no-launch`
  * **Expected Output:** Environment failure, exit code 3
  * **Actual Output:** `[FAIL] vivado_discovery: configured Vivado (cli) not found; doctor: environment problems found (exit 3)`
  * **Exit Code:** `3` (PASS)
* **Command:** `vicode doctor` with invalid configuration + invalid vivado
  * **Expected Output:** Configuration failure takes precedence over environment failure, exit code 2
  * **Actual Output:** `[FAIL] project_config: ... unknown key; [FAIL] vivado_discovery: ... not found; doctor: configuration problems found; fix them first (exit 2)`
  * **Exit Code:** `2` (PASS)
* **Command:** `vicode doctor` (real Vivado batch execution)
  * **Expected Output:** Vivado batch execution runs `environment.tcl`, prints `VICODE:begin`, extracts `version -short`, prints `VICODE:end`, logs written to `build/logs/environment.log`.
  * **Actual Output:** `[ OK ] vivado_probe: Vivado 2018.2 ran the Tcl probe in 25.2s; log: build/logs/environment.log; doctor: environment is ready (1 warning) (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode doctor` in `optproj` (Target Part: `xc7z020clg400-1`)
  * **Expected Output:** `get_parts -quiet xc7z020clg400-1` evaluates to 1, target part check OK
  * **Actual Output:** `[ OK ] target_part: part xc7z020clg400-1 is available; doctor: environment is ready (1 warning) (exit 0)`
  * **Exit Code:** `0` (PASS)
* **Command:** `vicode doctor` in `badpart` (Target Part: `xc7z999nonexistent`)
  * **Expected Output:** `get_parts` evaluates to 0, target part check FAIL, exit code 3
  * **Actual Output:** `[FAIL] target_part: part xc7z999nonexistent is not available in this Vivado installation; doctor: environment problems found (exit 3)`
  * **Exit Code:** `3` (PASS)
* **Command:** `vicode doctor --timeout 0.5`
  * **Expected Output:** Timeout triggered, process tree killed via `taskkill /PID <pid> /T /F`, no zombie processes remain, exit code 3
  * **Actual Output:** `[FAIL] vivado_probe: Vivado did not finish within 0.5s and was stopped; doctor: environment problems found (exit 3)`
  * **Process Cleanup Check:** `Get-Process -Name *vivado*, *hw_server*, *loader*` returned empty.
  * **Exit Code:** `3` (PASS)
