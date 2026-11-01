# Test report - Vi-Code 0.1.0

Generated 2026-11-01 12:18 UTC in the build sandbox.

| Environment | |
|---|---|
| OS | Linux 6.18.44-fc-v185 (NOT Windows 11) |
| Python | 3.12.3 |
| Vivado | none - a fake `vivado` (tests/fakes/fake_vivado.py) is used |
| Command | `python -X dev -W error -m unittest discover -s tests -t . -v` |

## Result: OK - 114 passed, 1 skipped, 0 failed

| Test module | Passed | Skipped | Other |
|---|---|---|---|
| test_cli | 21 | 0 | 0 |
| test_config | 21 | 0 | 0 |
| test_discovery | 11 | 0 | 0 |
| test_doctor | 28 | 0 | 0 |
| test_integration_real_vivado | 0 | 1 | 0 |
| test_jobs | 10 | 0 | 0 |
| test_process | 13 | 0 | 0 |
| test_tcl_and_messages | 10 | 0 | 0 |

The one skipped test is `test_integration_real_vivado`, which only runs when `VICODE_REAL_VIVADO=1`
on a machine with a real Vivado installation (see docs/verification.md).

## Additional checks performed

* Full suite re-run with Python dev mode and warnings as errors: clean (no leaked resources or warnings).
* Process/doctor/jobs tests repeated 5 times: no flaky failures.
* Suite run from a different working directory, and from an extracted copy of the release zip.
* Wheel built offline, installed into a clean virtual environment; `vicode --version`, `init`, `project validate`,
  `doctor --json` and a planned command ran from the installed package; packaged schema and compatibility
  matrix files load from the installed wheel.

## Bugs found by the tests and fixed before release

1. `vicode init` wrote a manifest with an empty `target:` section that `vicode project validate` rejected.
2. `vicode project` (no action) exited 0 instead of the documented usage-error code 2.
3. Hardening: Vivado file arguments are now short relative names so paths with spaces never reach the
   Windows batch-launcher command line (regression test added).

## NOT verified (honest limits)

Nothing has run on real Windows 11 or against real Vivado. The compatibility matrix is therefore empty and
`vicode doctor` reports "untested". The Windows-only code paths (`taskkill` tree termination, `pid_alive` via
ctypes, `.bat` launching) and the assumed default install folders, Vivado batch options, probe Tcl and message
formats are unconfirmed. See docs/verification.md for the checklist that closes milestone M0.
