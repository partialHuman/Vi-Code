"""Vi-Code M0: Thin end-to-end Project Mode counter synthesis spike CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add src to sys.path if not present
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from vicode.vivado.spike import run_spike


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="m0_counter_spike",
        description="Vi-Code M0: Thin end-to-end Project Mode counter synthesis spike.",
    )
    parser.add_argument(
        "--project-dir",
        "-p",
        metavar="DIR",
        default=".",
        help="Target directory for project and build layout (default: current directory)",
    )
    parser.add_argument(
        "--part",
        metavar="PART",
        default=None,
        help="Target FPGA part (default: xc7a35tcpg236-1)",
    )
    parser.add_argument(
        "--vivado",
        metavar="PATH",
        default=None,
        help="Explicit path to vivado or vivado.bat executable",
    )
    parser.add_argument(
        "--timeout",
        metavar="SECONDS",
        type=float,
        default=600.0,
        help="Maximum timeout in seconds for synthesis execution (default: 600.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output OperationResult in Protocol 1 JSON format to stdout",
    )

    args = parser.parse_args(argv)

    result = run_spike(
        root=args.project_dir,
        part=args.part,
        timeout=args.timeout,
        vivado_bin=args.vivado,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status_tag = f"[{result.status.upper()}]"
        print(f"{status_tag} {result.summary}")
        if result.exit_code is not None:
            print(f"Vivado Exit Code: {result.exit_code}")
        if result.target_part:
            print(f"Target Part: {result.target_part}")
        if result.tool_version:
            print(f"Tool Version: Vivado {result.tool_version}")
        if result.artifacts:
            print(f"Synthesized Checkpoint: {result.artifacts[0]}")
        if result.reports:
            print(f"Utilization Report: {result.reports[0]}")
        if result.details.get("utilization"):
            print("Resource Utilization:")
            for k, v in result.details["utilization"].items():
                print(f"  {k}: {v}")
        if result.diagnostics:
            print(f"Diagnostics ({len(result.diagnostics)}):")
            for d in result.diagnostics:
                d_id = f" [{d.id}]" if d.id else ""
                print(f"  {d.severity.upper()}{d_id}: {d.message}")

    return result.vicode_exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
