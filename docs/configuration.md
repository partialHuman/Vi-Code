# Configuration reference

## Project manifest: `vicode.yaml`

The manifest is the source of truth for a project. Unknown keys are errors; duplicate keys are errors.

```yaml
schema_version: 1            # required; this release supports 1
project:
  name: FlexRISC32           # required; letters, digits, _ and -, starting with a letter
  top_module: flexrisc32_top # optional; a module name
  hdl: SystemVerilog         # Verilog | SystemVerilog | VHDL
target:
  part: xc7z020clg400-1      # optional in 0.1
  board: pynq-z2             # optional
vivado:
  executable: auto           # "auto" or a path - honoured only if the project is trusted
  mode: project
sources:                     # relative globs with forward slashes; no absolute paths, no ".."
  rtl: ["rtl/**/*.v", "rtl/**/*.sv"]
  testbenches: ["sim/**/*.sv"]
  constraints: ["constraints/**/*.xdc"]
simulation:
  top: tb_flexrisc32
  simulator: xsim
build:
  jobs: 4                    # >= 1
  run_synthesis: true
  run_implementation: true
  generate_bitstream: false
```

Defaults for omitted keys are listed in `src/vicode/config.py`. In 0.1 the `sources`, `simulation` and `build`
sections are validated and recorded but not yet acted on.

The JSON Schema is `src/vicode/data/vicode.schema.json` (also shipped inside the installed package). To get
validation and completion in VS Code now, install a YAML extension and add to your settings:

```json
"yaml.schemas": { "C:/path/to/vicode.schema.json": "vicode.yaml" }
```

Later releases generate this setting for you.

## User configuration

Location: `%APPDATA%\vicode\config.yaml` on Windows, `$XDG_CONFIG_HOME/vicode/config.yaml` (or `~/.config/...`)
elsewhere. Override with the `VICODE_USER_CONFIG` environment variable.

```yaml
schema_version: 1
vivado:
  executable: C:/Xilinx/Vivado/2023.2/bin/vivado.bat   # always honoured
  search_paths: ["D:/tools/Xilinx/Vivado"]             # extra folders scanned for installations
trusted_projects: ["C:/work/blinky"]                   # managed by `vicode project trust`
```

## Precedence and trust

Highest first: command line (`--vivado`), project manifest (trusted projects only), user configuration, auto-discovery.
A manifest in an untrusted project cannot select the program Vi-Code runs: the setting is ignored with a warning.
Run `vicode project trust` in a project you trust to allow it.
