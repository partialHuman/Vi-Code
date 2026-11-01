"""``vicode init``: create a Vi-Code workspace (directories and manifest only; no Vivado project yet)."""

from __future__ import annotations

import json
from pathlib import Path

from vicode import config

DIRS = ("rtl", "sim", "constraints", "ip", "scripts")


class ScaffoldError(Exception):
    pass


def _q(value: str) -> str:
    return json.dumps(value)  # a JSON string is a valid, always-quoted YAML scalar


def manifest_text(name: str, hdl: str, part: str | None, board: str | None, top: str | None) -> str:
    lines = [
        "# Vi-Code project manifest. This file is the source of truth for the project;",
        "# the Vivado project is generated from it. Reference: docs/configuration.md",
        f"schema_version: {config.SCHEMA_VERSION}",
        "",
        "project:",
        f"  name: {_q(name)}",
    ]
    lines.append(f"  top_module: {_q(top)}" if top else '  # top_module: "my_top"')
    lines.append(f"  hdl: {_q(hdl)}")
    if part or board:
        lines += ["", "target:"]
        lines.append(f"  part: {_q(part)}" if part else '  # part: "xc7z020clg400-1"')
        lines.append(f"  board: {_q(board)}" if board else '  # board: "vendor:board:part0:1.0"')
    else:  # an empty "target:" would be invalid, so keep the example fully commented out
        lines += ["", "# target:", '#   part: "xc7z020clg400-1"', '#   board: "vendor:board:part0:1.0"']
    lines += [
        "",
        "vivado:",
        '  executable: "auto"  # a custom path is honoured only from user config or a trusted project',
        '  mode: "project"',
        "",
        "sources:",
        "  rtl:",
        '    - "rtl/**/*.v"',
        '    - "rtl/**/*.sv"',
        '    - "rtl/**/*.vhd"',
        "  testbenches:",
        '    - "sim/**/*.sv"',
        '    - "sim/**/*.v"',
        '    - "sim/**/*.vhd"',
        "  constraints:",
        '    - "constraints/**/*.xdc"',
        "",
        "build:",
        "  jobs: 4",
        "  run_synthesis: true",
        "  run_implementation: true",
        "  generate_bitstream: false",
        "",
    ]
    return "\n".join(lines)


def create_project(
    target: Path,
    name: str,
    hdl: str = "SystemVerilog",
    part: str | None = None,
    board: str | None = None,
    top: str | None = None,
) -> list[Path]:
    """Create the workspace at ``target`` and return the files and directories created."""
    data: dict = {"schema_version": config.SCHEMA_VERSION, "project": {"name": name, "hdl": hdl}}
    if top:
        data["project"]["top_module"] = top
    if part or board:
        data["target"] = {k: v for k, v in (("part", part), ("board", board)) if v}
    issues = config.validate_project_dict(data)
    if issues:
        raise config.ConfigError(issues)

    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ScaffoldError(f"{target} already exists and is not an empty directory")
    created: list[Path] = []
    target.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (target / d).mkdir()
        (target / d / ".gitkeep").write_text("", encoding="utf-8")
        created.append(target / d)
    files = {
        config.PROJECT_FILE: manifest_text(name, hdl, part, board, top),
        ".gitignore": "# Vi-Code build output (generated)\nbuild/\n",
        "README.md": (f"# {name}\n\nFPGA project managed with Vi-Code.\n\n"
                      "```\nvicode doctor            # check the environment\n"
                      "vicode project validate  # check vicode.yaml\n```\n"),
    }
    for filename, text in files.items():
        (target / filename).write_text(text, encoding="utf-8", newline="\n")
        created.append(target / filename)
    return created
