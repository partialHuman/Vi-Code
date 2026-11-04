"""Command-line interface (design Section 10.1)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path
from typing import Callable

from vicode import __version__, config, doctor as doctor_mod, scaffold
from vicode.events import EventSink
from vicode.results import Diagnostic, ExitCode, OperationResult

if sys.platform == "win32":
    os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")

# Commands that exist in the CLI skeleton but arrive in later product releases.
PLANNED: dict[str, str] = {
    "project import": "0.2", "source list": "0.2", "status": "0.2", "cancel": "0.2", "clean": "0.2",
    "tcl export": "0.2", "vivado open": "0.2", "sim": "0.3", "synth": "0.3", "impl": "0.4",
    "bitstream": "0.4", "build": "0.4", "report": "0.4", "hardware list": "0.6", "hardware program": "0.6",
}

_MARK = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}


# --- parser -------------------------------------------------------------------------------
def _output_parent() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("output")
    g.add_argument("--json", action="store_true", help="print the final result as JSON")
    g.add_argument("--json-stream", action="store_true",
                   help="print job events as JSON lines (the last event carries the result)")
    return p


def _project_parent() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--project-dir", metavar="DIR", help="project folder (default: search upwards for vicode.yaml)")
    return p


def build_parser() -> argparse.ArgumentParser:
    out, proj = _output_parent(), _project_parent()
    parser = argparse.ArgumentParser(prog="vicode", description="Vi-Code: Vivado workflows for VS Code and the command line.")
    parser.add_argument("--version", action="version", version=f"vicode {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    d = sub.add_parser("doctor", parents=[out, proj], help="check Vivado and the environment")
    d.add_argument("--vivado", metavar="PATH", help="vivado launcher or install folder to use")
    d.add_argument("--no-launch", action="store_true", help="do not start Vivado (fast checks only)")
    d.add_argument("--timeout", type=float, default=120.0, metavar="SEC", help="Vivado probe timeout (default 120)")

    i = sub.add_parser("init", parents=[out], help="create a new project workspace")
    i.add_argument("name", help="project name")
    i.add_argument("--dir", metavar="DIR", help="target folder (default: ./NAME)")
    i.add_argument("--hdl", choices=config.HDLS, default="SystemVerilog")
    i.add_argument("--part", metavar="PART")
    i.add_argument("--board", metavar="BOARD")
    i.add_argument("--top", metavar="MODULE", help="top module name")

    pr = sub.add_parser("project", help="project commands").add_subparsers(dest="action", metavar="<action>")
    pr.add_parser("validate", parents=[out, proj], help="validate vicode.yaml")
    pr.add_parser("trust", parents=[out, proj],
                  help="trust project executable settings and permit Git clean filters",
                  description="Mark project as trusted, allowing project-specified Vivado executables and permitting Git metadata operations to execute repository-defined clean filters.")
    pr.add_parser("import", parents=[out], help="(planned) import an existing Vivado project").add_argument("rest", nargs="*")

    for top, actions in (("source", ["list"]), ("tcl", ["export"]), ("vivado", ["open"]),
                         ("hardware", ["list", "program"])):
        s = sub.add_parser(top, help="(planned)").add_subparsers(dest="action", metavar="<action>")
        for a in actions:
            s.add_parser(a, parents=[out], help="(planned)").add_argument("rest", nargs="*")
    for name in ("sim", "synth", "impl", "bitstream", "build", "report", "status", "cancel", "clean"):
        sub.add_parser(name, parents=[out], help="(planned)").add_argument("rest", nargs="*")
    return parser


# --- output ------------------------------------------------------------------------------
def render_text(result: OperationResult) -> str:
    lines: list[str] = []
    checks = result.details.get("checks")
    if checks:
        for c in checks:
            lines.append(f"  {_MARK.get(c['status'], '[ ?? ]')} {c['name']}: {c['message']}")
            if c.get("hint") and c["status"] in ("warn", "fail"):
                lines.append(f"         hint: {c['hint']}")
    else:
        for d in result.diagnostics:
            lines.append(f"  {d.severity.upper()}: {d.message}" + (f"\n         hint: {d.hint}" if d.hint else ""))
    for log in result.logs:
        lines.append(f"  log: {log}")
    head = f"{result.operation}: {result.summary}  (exit {result.vicode_exit_code})"
    return "\n".join(lines + ["", head]) if lines else head


def _run(args: argparse.Namespace, operation: str, fn: Callable[[EventSink], OperationResult]) -> int:
    is_json_stream = getattr(args, "json_stream", False)
    is_json = getattr(args, "json", False)
    sink = EventSink(stream=sys.stdout if is_json_stream else None)
    is_internal_error = False
    try:
        result = fn(sink)
    except KeyboardInterrupt:
        result = OperationResult(operation, tool=None).finish(ExitCode.CANCELLED, "cancelled")
        sink.finished(result.status, int(ExitCode.CANCELLED), result.to_dict())
    except Exception as exc:
        if os.environ.get("VICODE_DEBUG"):
            raise
        is_internal_error = True
        result = OperationResult(operation, tool=None)
        err_msg = f"internal error: {type(exc).__name__}: {exc}"
        diag = Diagnostic("error", err_msg, category="internal")
        result.diagnostics.append(diag)
        result.finish(ExitCode.FAILED, err_msg)
        sink.message(diag)
        sink.finished(result.status, int(ExitCode.FAILED), result.to_dict())
    if is_json_stream:
        pass  # the events, including job.finished, were already streamed
    elif is_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        out = sys.stderr if is_internal_error else sys.stdout
        print(render_text(result), file=out)
    return result.vicode_exit_code


def _simple(operation: str, sink: EventSink, build: Callable[[OperationResult], tuple[ExitCode, str]]) -> OperationResult:
    sink.started(operation)
    result = OperationResult(operation, tool=None)
    code, summary = build(result)
    result.finish(code, summary)
    for d in result.diagnostics:
        sink.message(d)
    sink.finished(result.status, int(code), result.to_dict())
    return result


# --- command handlers --------------------------------------------------------------------
def cmd_doctor(args: argparse.Namespace) -> int:
    cancel = threading.Event()
    opts = doctor_mod.DoctorOptions(
        cwd=Path.cwd(), project_dir=Path(args.project_dir) if args.project_dir else None,
        vivado=args.vivado, launch=not args.no_launch, timeout=args.timeout, cancel=cancel)
    return _run(args, "doctor", lambda sink: doctor_mod.run_doctor(opts, sink))


def _project_root(args: argparse.Namespace) -> Path | None:
    return Path(args.project_dir).resolve() if args.project_dir else config.find_project_root(Path.cwd())


def cmd_validate(args: argparse.Namespace) -> int:
    def build(result: OperationResult) -> tuple[ExitCode, str]:
        root = _project_root(args)
        if root is None or not (root / config.PROJECT_FILE).is_file():
            result.diagnostics.append(Diagnostic("error", f"no {config.PROJECT_FILE} found",
                                                 category="configuration", hint="Run 'vicode init' or use --project-dir"))
            return ExitCode.USAGE_OR_CONFIG, f"no {config.PROJECT_FILE} found"
        loaded = config.load_project(root)
        result.details["path"] = str(loaded.path)
        if loaded.ok:
            result.target_part = loaded.config.part
            result.details["resolved"] = loaded.config.resolved()
            return ExitCode.OK, f"{loaded.path} is valid"
        for issue in loaded.issues:
            result.diagnostics.append(Diagnostic("error", str(issue), category="configuration",
                                                 file=str(loaded.path), line=issue.line))
        return ExitCode.USAGE_OR_CONFIG, f"{len(loaded.issues)} problem(s) in {loaded.path}"

    return _run(args, "project.validate", lambda sink: _simple("project.validate", sink, build))


def cmd_trust(args: argparse.Namespace) -> int:
    def build(result: OperationResult) -> tuple[ExitCode, str]:
        root = _project_root(args)
        if root is None:
            result.diagnostics.append(Diagnostic("error", f"no {config.PROJECT_FILE} found", category="configuration"))
            return ExitCode.USAGE_OR_CONFIG, f"no {config.PROJECT_FILE} found"
        path = config.user_config_path()
        try:
            config.add_trusted_project(path, root)
        except config.ConfigError as exc:
            result.diagnostics.append(Diagnostic("error", f"user configuration is invalid: {exc}", category="configuration"))
            return ExitCode.USAGE_OR_CONFIG, "user configuration is invalid"
        result.details.update({"trusted": str(root), "user_config": str(path)})
        return ExitCode.OK, f"trusted {root} (recorded in {path})"

    return _run(args, "project.trust", lambda sink: _simple("project.trust", sink, build))


def cmd_init(args: argparse.Namespace) -> int:
    def build(result: OperationResult) -> tuple[ExitCode, str]:
        target = Path(args.dir) if args.dir else Path.cwd() / args.name
        try:
            created = scaffold.create_project(target, args.name, args.hdl, args.part, args.board, args.top)
        except config.ConfigError as exc:
            for issue in exc.issues:
                result.diagnostics.append(Diagnostic("error", str(issue), category="configuration"))
            return ExitCode.USAGE_OR_CONFIG, "invalid project settings"
        except (scaffold.ScaffoldError, OSError) as exc:
            result.diagnostics.append(Diagnostic("error", str(exc), category="project"))
            return ExitCode.FAILED, "could not create the project"
        result.details["project_dir"] = str(target.resolve())
        result.details["created"] = [str(p.relative_to(target)) for p in created]
        return ExitCode.OK, f"created {target} - next: cd into it and run 'vicode doctor'"

    return _run(args, "init", lambda sink: _simple("init", sink, build))


def cmd_planned(args: argparse.Namespace, key: str) -> int:
    release = PLANNED[key]

    def build(result: OperationResult) -> tuple[ExitCode, str]:
        msg = f"'vicode {key}' is planned for release {release} and is not available in release {__version__[:3]}"
        result.diagnostics.append(Diagnostic("error", msg, category="usage"))
        return ExitCode.NOT_AVAILABLE, msg

    return _run(args, key.replace(" ", "."), lambda sink: _simple(key.replace(" ", "."), sink, build))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return int(ExitCode.USAGE_OR_CONFIG)
    try:
        if args.command == "doctor":
            return cmd_doctor(args)
        if args.command == "init":
            return cmd_init(args)
        if args.command == "project" and args.action == "validate":
            return cmd_validate(args)
        if args.command == "project" and args.action == "trust":
            return cmd_trust(args)
        key = args.command if getattr(args, "action", None) is None else f"{args.command} {args.action}"
        if key in PLANNED:
            return cmd_planned(args, key)
        try:  # incomplete nested command: show that command's help, but report a usage error
            parser.parse_args([args.command, "--help"])
        except SystemExit:
            pass
        return int(ExitCode.USAGE_OR_CONFIG)
    except Exception as exc:  # pragma: no cover - last-resort guard
        if os.environ.get("VICODE_DEBUG"):
            raise
        raw_args = argv if argv is not None else sys.argv[1:]
        is_stream = "--json-stream" in raw_args
        is_json = "--json" in raw_args
        err_msg = f"internal error: {type(exc).__name__}: {exc}"
        if is_stream or is_json:
            result = OperationResult("cli", tool=None)
            diag = Diagnostic("error", err_msg, category="internal")
            result.diagnostics.append(diag)
            result.finish(ExitCode.FAILED, err_msg)
            if is_stream:
                sink = EventSink(stream=sys.stdout)
                sink.message(diag)
                sink.finished(result.status, int(ExitCode.FAILED), result.to_dict())
            else:
                print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"{err_msg}. Set VICODE_DEBUG=1 for a traceback.", file=sys.stderr)
        return int(ExitCode.FAILED)


if __name__ == "__main__":
    sys.exit(main())
