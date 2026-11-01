# Vi-Code 0.1.0 — Windows Installation Report

**Date:** 2026-11-01<br>
**Project:** Vi-Code 0.1.0<br>
**Workspace:** `C:\Users\User\Documents\Projects\Vi-Code`<br>
**Target Platform:** Windows 11 (build 26300, 64-bit)<br>

---

## 1. Environment Details

| Component | Detected / Used Version | Path / Location |
|---|---|---|
| **Operating System** | Windows 11 (build 26300) | `Microsoft Windows NT 10.0.26300.0` |
| **Python Launcher** | `py.exe` | System PATH |
| **Active Python** | Python 3.14.7 (64-bit) | `C:\Python314\python.exe` |
| **Other Available Pythons** | Python 3.13, 3.12, 3.11, 3.9 | Detected via `py -0p` |
| **Virtual Environment** | Isolated `.venv` | `C:\Users\User\Documents\Projects\Vi-Code\.venv` |
| **Package Installer (pip)** | pip 26.2.2 (upgraded from 26.2.1) | `.\.venv\Scripts\pip.exe` |
| **Build Backend** | `setuptools.build_meta` | Setuptools >= 61 (packaged with venv) |
| **Shell** | PowerShell 7 / Windows PowerShell | `pwsh.exe` |

---

## 2. Packaging Configuration Analysis

Inspection of `pyproject.toml` showed:
* **Project Name:** `vicode`
* **Version:** `0.1.0`
* **Requires-Python:** `>=3.11` (Python 3.14.7 satisfies this requirement)
* **Declared Runtime Dependencies:** `["PyYAML>=6.0"]`
* **Optional Development Dependencies:** None declared in `pyproject.toml`
* **Build System:** `requires = ["setuptools>=61"]`, `build-backend = "setuptools.build_meta"`
* **CLI Entry Points:** `vicode = "vicode.cli:main"`
* **Package Discovery:** `tool.setuptools.packages.find` with `where = ["src"]`
* **Package Data:** `vicode = ["data/*.json"]` (`compat_matrix.json`, `vicode.schema.json`)

---

## 3. Installation Procedure

### 3.1 Virtual Environment Creation

Virtual environment `.venv` was created in the project root:

```powershell
py -m venv .venv
```
* **Command Output:** None (clean exit 0).
* **Target Directory:** `C:\Users\User\Documents\Projects\Vi-Code\.venv`

### 3.2 Activation and pip Upgrade

Activated `.venv` and upgraded pip to the latest available wheel:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

**Command Output:**
```text
Requirement already satisfied: pip in .\.venv\Lib\site-packages (26.2.1)
Collecting pip
  Using cached pip-26.2.2-py3-none-any.whl.metadata (4.6 kB)
Using cached pip-26.2.2-py3-none-any.whl (1.8 MB)
Installing collected packages: pip
  Attempting uninstall: pip
    Found existing installation: pip 26.2.1
    Uninstalling pip-26.2.1:
      Successfully uninstalled pip-26.2.1
Successfully installed pip-26.2.2
```

### 3.3 Editable Package Installation

Installed Vi-Code in editable mode from the local workspace repository without using any published PyPI package:

```powershell
python -m pip install -e .
```

**Command Output:**
```text
Obtaining file:///C:/Users/User/Documents/Projects/Vi-Code
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Checking if build backend supports build_editable: started
  Checking if build backend supports build_editable: finished with status 'done'
  Getting requirements to build editable: started
  Getting requirements to build editable: finished with status 'done'
  Preparing editable metadata (pyproject.toml): started
  Preparing editable metadata (pyproject.toml): finished with status 'done'
Collecting PyYAML>=6.0 (from vicode==0.1.0)
  Using cached pyyaml-6.0.3-cp314-cp314-win_amd64.whl.metadata (2.4 kB)
Using cached pyyaml-6.0.3-cp314-cp314-win_amd64.whl (156 kB)
Building wheels for collected packages: vicode
  Building editable for vicode (pyproject.toml): started
  Building editable for vicode (pyproject.toml): finished with status 'done'
  Created wheel for vicode: filename=vicode-0.1.0-0.editable-py3-none-any.whl size=3411 sha256=390c858503d2680096c99877a8be795f0154676e884a40772b90e7188c8fb3a9
  Stored in directory: C:\Users\User\AppData\Local\Temp\pip-ephem-wheel-cache-068e7oww\wheels\aa\16\e8\d3f34e13c79dcc46785362353102683fab2487cb576c87b76b
Successfully built vicode
Installing collected packages: PyYAML, vicode
Successfully installed PyYAML-6.0.3 vicode-0.1.0
```

---

## 4. Installed Dependency Verification

Verified via `python -m pip list`:

| Package | Installed Version | Source Location / Status |
|---|---|---|
| `pip` | `26.2.2` | `.venv\Lib\site-packages` |
| `PyYAML` | `6.0.3` | `.venv\Lib\site-packages` (precompiled C-extension wheel for cp314-win_amd64) |
| `vicode` | `0.1.0` | Editable (`C:\Users\User\Documents\Projects\Vi-Code`) |

Verified entry point executable generation:
* Launcher executable created at `C:\Users\User\Documents\Projects\Vi-Code\.venv\Scripts\vicode.exe`.

---

## 5. Installation Outcome & Warnings

* **Status:** PASS
* **Exit Code:** 0
* **Warnings:** 0
* **Errors:** 0
* **Compatibility Notes:** Python 3.14.7 was detected as default and met `>=3.11`. `PyYAML 6.0.3` had official wheels for Python 3.14 on Windows AMD64, allowing a completely frictionless local installation.
