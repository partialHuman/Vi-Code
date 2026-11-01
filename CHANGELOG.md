# Changelog

## 0.1.0 - Foundation (milestones M0-M1)

First release.

* `vicode doctor`: platform, user/project configuration, Vivado discovery (configured path, user search paths,
  `XILINX_VIVADO`, `PATH`, default roots), launcher check, compatibility matrix lookup, batch-mode Tcl probe,
  target-part check, diagnostics from Vivado messages.
* `vicode init`, `vicode project validate`, `vicode project trust`.
* Strict `vicode.yaml` loading (safe YAML, duplicate keys rejected, unknown keys rejected, `schema_version`),
  published JSON Schema, configuration precedence and a project trust boundary.
* Process runner: argument lists only, batch-launcher argument validation, environment allowlist, relative file
  arguments, timeout, cancellation and whole-process-tree termination.
* Structured results and job events (protocol 1), build records, per-project lock with stale-lock recovery.
* CLI skeleton with planned commands, documented exit codes, `--json` and `--json-stream`.
* Test suite with a fake Vivado; opt-in real-Vivado integration test.

Not yet verified on real Windows 11 + Vivado (see docs/verification.md).
