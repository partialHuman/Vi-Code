# Verification status and the M0 checklist

## What has been verified (automated)

* 114 unit and contract tests (plus 1 opt-in real-Vivado test, skipped) on Linux (Python 3.12) against a fake `vivado`: configuration, Tcl quoting,
  message parsing, discovery logic, process control (timeout, cancel, whole-tree termination), project lock,
  build records, `doctor` end to end, and the CLI.
* Packaging: the wheel builds, installs into a clean virtual environment and runs.

## What has NOT been verified

Nothing has run on real Windows 11 or against a real Vivado. These are assumptions to confirm (milestone M0):

1. Default install folders searched on Windows (`C:\Xilinx\Vivado\<ver>`, `C:\AMD\...`, and the `<ver>\Vivado` layout).
2. Vivado accepts the batch options used: `-mode batch -source -log -journal -tempDir -notrace`, with relative file names.
3. The probe Tcl: `version -short` and `get_parts -quiet <part>` print what the doctor expects.
4. `.bat` launching: a launcher path containing spaces or parentheses; `taskkill /T /F` ends Vivado and its children.
5. Vivado message formats parsed by `vicode.vivado.messages` match real logs (the fixtures are synthetic).
6. How long the first start takes (default doctor timeout is 120 s).
7. Windows-only code paths: `jobs.pid_alive` (ctypes) and console output encoding.

## Checklist (run on the Windows 11 machine that has Vivado)

```
py -m pip install .
python -m unittest discover -s tests -t . -v            # all must pass (1 skipped)
set VICODE_REAL_VIVADO=1
python -m unittest tests.test_integration_real_vivado -v
vicode doctor --json > doctor.json
```

Then:

1. Run `vicode doctor` from a folder whose path contains spaces, with a project (`vicode init`) that sets a real `--part`.
2. Press Ctrl+C during the probe and confirm no `vivado`/`java`/`hw_server` process remains in Task Manager.
3. Run with `--timeout 1` and confirm the same.
4. Install a second Vivado version (if available) and confirm discovery lists both and `--vivado` selects either.
5. Record the measured probe time (`details.probe_seconds`).

When all pass, add the combination to `src/vicode/data/compat_matrix.json`, for example:

```json
{"os": "windows-11", "vivado": "2023.2", "status": "verified", "evidence": "M0 checklist, <date>"}
```

and send the `doctor.json` plus any parser mismatches so the fixtures can be replaced with recorded logs.
