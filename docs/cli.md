# CLI reference (release 0.1.0)

## Commands

Available now: `--version`, `doctor`, `init`, `project validate`, `project trust`.

Planned (the command exists but exits with code 5): `project import` (0.2), `source list` (0.2), `status` (0.2),
`cancel` (0.2), `clean` (0.2), `tcl export` (0.2), `vivado open` (0.2), `sim` (0.3), `synth` (0.3),
`impl` (0.4), `bitstream` (0.4), `build` (0.4), `report` (0.4), `hardware list` (0.6), `hardware program` (0.6).

## Common options

| Option | Meaning |
|---|---|
| `--json` | Print the final result as one JSON document. |
| `--json-stream` | Print job events as JSON lines; the last event carries the result. |
| `--project-dir DIR` | Project folder (default: search upwards from the current folder for `vicode.yaml`). |

`doctor` also takes `--vivado PATH` (launcher, install folder or its `bin`), `--no-launch` (never start Vivado)
and `--timeout SEC` (default 120).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | The operation ran and failed (or an unexpected error). |
| 2 | Invalid usage or invalid configuration. |
| 3 | Environment problem (Vivado missing or not working). |
| 4 | Cancelled (for example Ctrl+C). |
| 5 | The command exists but is not available in this release. |

When `doctor` finds both a configuration and an environment problem it returns 2: fix the configuration first.

## Result document (protocol 1)

```json
{
  "protocol": 1, "vicode_version": "0.1.0", "operation": "doctor", "status": "succeeded",
  "tool": "vivado", "tool_version": "2023.2", "target_part": "xc7z020clg400-1",
  "started_at": "...", "finished_at": "...", "exit_code": 0, "vicode_exit_code": 0,
  "logs": ["build/logs/environment.log"], "reports": [], "artifacts": ["build/vivado/environment.tcl"],
  "diagnostics": [{"severity": "warning", "message": "...", "category": "environment", "hint": "..."}],
  "summary": "environment is ready (2 warnings)", "details": {"checks": [...]}
}
```

`exit_code` is the external tool's status; `vicode_exit_code` is the exit code of `vicode` itself. `status` is
`succeeded`, `failed` or `cancelled`. Diagnostics use the severities `info`, `warning`, `critical_warning`, `error`
and carry the Vivado message id (for example `Synth 8-3332`), file and line when Vivado provided them.

## Job events (protocol 1)

Every event has `protocol`, `event`, `job_id` and `ts`. Clients must check `protocol` first.

```
{"event": "job.started",  "operation": "doctor"}
{"event": "job.stage",    "stage": "vivado_probe"}
{"event": "job.message",  "severity": "warning", "message": "...", "id": "Synth 8-3332", "file": "rtl/top.sv", "line": 12}
{"event": "job.finished", "status": "succeeded", "vicode_exit_code": 0, "result": {...}, "result_path": "build/metadata/doctor-result.json"}
```

## What `doctor` checks

`python`, `platform`, `user_config`, `project_config`, `vivado_setting`, `vivado_discovery`, `vivado_launcher`,
`compatibility`, `vivado_probe`, `vivado_version`, `target_part`. Each is `ok`, `warn`, `fail` or `skip`.
The probe starts Vivado in batch mode with a small Tcl script and requires its marker lines; the target part is
checked with `get_parts`. Licence availability is not checked in 0.1.

Inside a project, `doctor` writes `build/logs/environment.log`, `build/vivado/environment.tcl` and
`build/metadata/doctor-result.json`, and holds `build/.vicode.lock` while Vivado runs.
