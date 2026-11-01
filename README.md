# Vi-Code

Vivado workflows for VS Code and the command line.

**Release 0.1.0 - "Foundation"** (roadmap milestones M0-M1). This release delivers the base every
later release builds on: strict configuration, Vivado discovery, a safe process runner,
structured results and job events, `vicode doctor`, and a test harness that needs no Vivado.
It does **not** yet create Vivado projects, simulate, synthesize, or program hardware - those commands
exist in the CLI but report that they are planned for a later release (see [docs/cli.md](docs/cli.md)).

> **Verification status:** all automated tests pass (115 tests: 114 run, 1 opt-in real-Vivado test skipped; Linux, fake Vivado). Nothing has been run
> against a real Windows 11 + Vivado machine yet - that is the open M0 exit criterion.
> Follow [docs/verification.md](docs/verification.md) to close it. Until then the compatibility
> matrix is intentionally empty and `vicode doctor` reports "untested".

## What works in 0.1.0

| Command | Purpose |
|---|---|
| `vicode --version` | Print the version. |
| `vicode doctor` | Find Vivado, run a Tcl probe in batch mode, check the target part, report problems. |
| `vicode init NAME` | Create a workspace: folders, `vicode.yaml`, `.gitignore`, `README.md`. |
| `vicode project validate` | Validate `vicode.yaml` strictly. |
| `vicode project trust` | Allow this project's `vivado.executable` setting to be honoured. |

All commands accept `--json` (final result) or `--json-stream` (job events as JSON lines).
Exit codes are documented in [docs/cli.md](docs/cli.md).

## Install (Windows 11)

Requires Python 3.11 or newer.

```
py -m pip install .
vicode --version
vicode doctor
```

or run from the source tree without installing: `set PYTHONPATH=src` then `py -m vicode doctor`.

## Quick start

```
vicode init blinky --part xc7z020clg400-1
cd blinky
vicode project validate
vicode doctor
```

`vicode doctor` looks for Vivado in this order: `--vivado PATH`, `vivado.executable` in your user
configuration, `XILINX_VIVADO`, `PATH`, then the default install folders. If it picks the wrong
installation, pass `--vivado C:\Xilinx\Vivado\2023.2` (or set it in the user configuration - see
[docs/configuration.md](docs/configuration.md)).

## Run the tests

```
python -m unittest discover -s tests -t . -v
```

Uses only the standard library plus PyYAML. The contract tests run `vicode` against a fake
`vivado` (`tests/fakes/fake_vivado.py`), so no Vivado licence or install is needed.
`tests/test_integration_real_vivado.py` is skipped unless `VICODE_REAL_VIVADO=1`.

## Design principles that are enforced by tests

* A zero exit status alone is never accepted as proof that Vivado worked (the probe must print its markers).
* A repository cannot choose which program Vi-Code executes unless you trust it.
* Cancel and timeout stop Vivado **and** everything it started.
* Only an allowlisted set of environment variables reaches Vivado; licence settings pass through and are never logged.
* Unknown configuration keys are errors, not silently ignored.

## Project layout

```
src/vicode/        package (cli, config, doctor, jobs, results, events, vivado/*)
tests/             unit + contract tests, fake Vivado
docs/              CLI, configuration and verification guides
scripts/           gen_schema.py (regenerates the JSON Schema)
```

## Licence

Not chosen yet (an open decision in the design document). Add a LICENSE file before publishing.

Vi-Code is an independent project and is not affiliated with, endorsed by or sponsored by AMD.
Vivado and Xilinx are trademarks of their respective owners. Vi-Code does not redistribute AMD software.
