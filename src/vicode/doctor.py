"""``vicode doctor``: verify the environment without ever trusting an exit status alone."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from vicode import compat, config, jobs, platform_info
from vicode.events import EventSink
from vicode.results import Diagnostic, ExitCode, OperationResult
from vicode.vivado import discovery, messages, tcl
from vicode.vivado.runner import run_tcl

MIN_PYTHON = (3, 11)


@dataclass
class DoctorOptions:
    cwd: Path
    project_dir: Path | None = None
    vivado: str | None = None
    launch: bool = True
    timeout: float = 120.0
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    user_config_path: Path | None = None
    extra_roots: tuple[str, ...] = ()
    include_default_roots: bool = True
    platform: platform_info.PlatformInfo | None = None
    which: Callable[[str], str | None] = shutil.which
    cancel: threading.Event | None = None
    work_dir: Path | None = None  # log location when there is no project


def run_doctor(opts: DoctorOptions, sink: EventSink) -> OperationResult:
    sink.started("doctor")
    result = OperationResult(operation="doctor")
    checks: list[dict[str, Any]] = []
    state = {"config_failed": False, "env_failed": False}

    def add(name: str, status: str, message: str, hint: str | None = None, kind: str = "env") -> None:
        checks.append({"name": name, "status": status, "message": message, **({"hint": hint} if hint else {})})
        if status in ("warn", "fail"):
            diag = Diagnostic("warning" if status == "warn" else "error", message,
                              category="configuration" if kind == "config" else "environment", hint=hint)
            result.diagnostics.append(diag)
            sink.message(diag)
        if status == "fail":
            state["config_failed" if kind == "config" else "env_failed"] = True

    env = opts.env
    plat = opts.platform or platform_info.detect()

    # 1. Python
    sink.stage("python")
    if sys.version_info >= MIN_PYTHON:
        add("python", "ok", f"Python {sys.version.split()[0]}")
    else:
        add("python", "warn", f"Python {sys.version.split()[0]} is older than the required "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}")

    # 2. Platform
    sink.stage("platform")
    if plat.is_windows11:
        add("platform", "ok", plat.label)
    elif plat.is_windows:
        add("platform", "warn", f"{plat.label}: release 0.1 is built and verified for Windows 11",
            "Use Windows 11 for supported behaviour")
    else:
        add("platform", "warn", f"{plat.label}: release 0.1 supports Windows 11 only; this host is for development use",
            "Ubuntu support is planned for milestone M10")

    # 3. User configuration
    sink.stage("user_config")
    user_path = opts.user_config_path or config.user_config_path(env, plat.is_windows)
    user = config.load_user(user_path)
    if user.issues:
        for issue in user.issues:
            add("user_config", "fail", f"{user_path}: {issue}", "Fix or remove the user configuration file", "config")
    elif user.exists:
        add("user_config", "ok", f"loaded {user_path}")
    else:
        add("user_config", "ok", f"no user configuration file ({user_path})")

    # 4. Project configuration
    sink.stage("project_config")
    root: Path | None = None
    project_cfg: config.ProjectConfig | None = None
    if opts.project_dir is not None:
        root = Path(opts.project_dir).resolve()
        if not (root / config.PROJECT_FILE).is_file():
            add("project_config", "fail", f"no {config.PROJECT_FILE} in {root}",
                "Run 'vicode init' or pass the correct --project-dir", "config")
            root = None
    else:
        root = config.find_project_root(opts.cwd)
    if root is not None:
        loaded = config.load_project(root)
        if loaded.ok:
            project_cfg = loaded.config
            result.target_part = project_cfg.part
            add("project_config", "ok", f"{loaded.path} is valid (project '{project_cfg.name}')")
        else:
            for issue in loaded.issues:
                add("project_config", "fail", f"{loaded.path}: {issue}",
                    "Run 'vicode project validate' for details", "config")
    elif opts.project_dir is None:
        add("project_config", "skip", f"no {config.PROJECT_FILE} found; project checks skipped")

    # 5. Which Vivado does the user want?
    resolved = config.resolve_vivado_executable(opts.vivado, project_cfg, root, user.config)
    for note in resolved.notes:
        add("vivado_setting", "warn", note)

    # 6. Discovery
    sink.stage("vivado_discovery")
    selected: discovery.Installation | None = None
    installs: list[discovery.Installation] = []
    if resolved.executable:
        selected = discovery.resolve_path(resolved.executable, plat.is_windows)
        if selected is None:
            add("vivado_discovery", "fail", f"configured Vivado ({resolved.source}) not found: {resolved.executable}",
                "Check the path points to vivado.bat, the install folder or its bin folder")
        else:
            installs = [selected]
            add("vivado_discovery", "ok", f"using Vivado from {resolved.source}: {selected.launcher}")
    else:
        installs = discovery.discover(
            env, plat.is_windows, None,
            extra_roots=tuple(opts.extra_roots) + tuple(user.config.search_paths),
            which=opts.which, include_default_roots=opts.include_default_roots)
        if not installs:
            add("vivado_discovery", "fail", "no Vivado installation found",
                "Install Vivado, add it to PATH, set XILINX_VIVADO, pass --vivado PATH, or set vivado.executable in your user configuration")
        else:
            selected = installs[0]
            more = f" ({len(installs) - 1} more found)" if len(installs) > 1 else ""
            add("vivado_discovery", "ok",
                f"found Vivado {selected.version or '(unknown version)'} at {selected.launcher} via {selected.source}{more}")
    result.details["installations"] = [
        {"launcher": i.launcher, "version": i.version, "source": i.source} for i in installs]

    # 7. Launcher + compatibility
    version = selected.version if selected else None
    if selected is not None:
        sink.stage("vivado_launcher")
        launcher_ok = os.path.isfile(selected.launcher) and (
            plat.is_windows or os.access(selected.launcher, os.X_OK))
        if launcher_ok:
            add("vivado_launcher", "ok", "launcher exists and is executable")
        else:
            add("vivado_launcher", "fail", f"{selected.launcher} is not an executable file")
            selected = None
    if selected is not None:
        sink.stage("compatibility")
        status, text = compat.check(version, plat)
        add("compatibility", "ok" if status == "verified" else "warn", text)
        result.details["compatibility"] = status

    # 8. Probe
    sink.stage("vivado_probe")
    layout: jobs.Layout | None = None
    cancelled = False
    if selected is None:
        add("vivado_probe", "skip", "skipped: no usable Vivado")
    elif not opts.launch:
        add("vivado_probe", "skip", "skipped (--no-launch): Vivado was not started")
    else:
        if root is not None:
            layout = jobs.build_layout(root)
        else:
            base = Path(opts.work_dir) if opts.work_dir else Path(tempfile.gettempdir()) / "vicode-doctor"
            layout = jobs.build_layout(base / sink.job_id)
        lock = jobs.ProjectLock(layout.build, "doctor") if root is not None else None
        try:
            if lock:
                lock.acquire()
            part = project_cfg.part if project_cfg else None
            run = run_tcl(selected.launcher, tcl.probe_script(part), layout, "environment", env,
                          timeout=opts.timeout, cancel=opts.cancel)
        except jobs.ProjectBusy as exc:
            add("vivado_probe", "fail", str(exc), "Wait for the other job to finish, or run 'vicode cancel'")
            run = None
        finally:
            if lock:
                lock.release()
        if run is not None:
            result.exit_code = run.outcome.exit_code
            result.logs.append(_rel(run.log, root))
            result.artifacts.append(_rel(run.script, root))
            seen = {(d.severity, d.id, d.message) for d in result.diagnostics}
            for diag in messages.parse_lines(run.lines):
                diag.category = "vivado"
                if (diag.severity, diag.id, diag.message) not in seen:
                    result.diagnostics.append(diag)
                    sink.message(diag)
            markers = tcl.parse_probe_output(run.lines)
            if run.outcome.error:
                add("vivado_probe", "fail", run.outcome.error)
            elif run.outcome.cancelled:
                cancelled = True
                add("vivado_probe", "warn", "cancelled")
            elif run.outcome.timed_out:
                add("vivado_probe", "fail", f"Vivado did not finish within {opts.timeout:g}s and was stopped",
                    "The first start can be slow; retry with a larger --timeout")
            elif run.outcome.exit_code != 0:
                add("vivado_probe", "fail", f"Vivado exited with status {run.outcome.exit_code}",
                    f"See {_rel(run.log, root)}")
            elif markers is None:
                add("vivado_probe", "fail",
                    "Vivado exited with status 0 but produced no probe output; an exit status alone is not proof "
                    "that Tcl ran", f"See {_rel(run.log, root)}")
            else:
                probed = markers.get("version")
                add("vivado_probe", "ok", f"Vivado {probed} ran the Tcl probe in {run.outcome.duration_s:.1f}s")
                result.tool_version = probed
                result.details["probe_seconds"] = round(run.outcome.duration_s, 3)
                if version and probed and version != probed:
                    add("vivado_version", "warn", f"install path suggests {version} but Vivado reports {probed}")
                if part:
                    if markers.get("part_found") == "1":
                        add("target_part", "ok", f"part {part} is available")
                    else:
                        add("target_part", "fail", f"part {part} is not available in this Vivado installation",
                            "Install device support for this part with the Vivado installer")
    if result.tool_version is None and selected is not None:
        result.tool_version = version

    # Result
    result.details["checks"] = checks
    result.details["platform"] = {"system": plat.system, "release": plat.release,
                                  "windows_build": plat.windows_build, "windows11": plat.is_windows11}
    result.details["vivado_setting_source"] = resolved.source
    if selected is not None:
        result.details["selected"] = {"launcher": selected.launcher, "version": selected.version,
                                      "source": selected.source}
    if root is not None and project_cfg is not None:
        result.details["project"] = {
            "root": str(root), "config_hash": jobs.config_hash(project_cfg.resolved()), "git": jobs.git_state(root)}

    if cancelled:
        code, summary = ExitCode.CANCELLED, "doctor was cancelled"
    elif state["config_failed"]:
        code, summary = ExitCode.USAGE_OR_CONFIG, "configuration problems found; fix them first"
    elif state["env_failed"]:
        code, summary = ExitCode.ENVIRONMENT, "environment problems found"
    else:
        warns = sum(1 for c in checks if c["status"] == "warn")
        code = ExitCode.OK
        summary = "environment is ready" + (f" ({warns} warning{'s' if warns != 1 else ''})" if warns else "")
    result.finish(code, summary)

    if root is not None:
        out_layout = jobs.build_layout(root)
        result.details["result_path"] = _rel(jobs.result_path(out_layout, "doctor"), root)
        jobs.write_result(out_layout, result)
    sink.finished(result.status, int(code), result.to_dict(), result.details.get("result_path"))
    return result


def _rel(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return Path(path).resolve().relative_to(root).as_posix()
        except ValueError:
            pass
    return str(path)
