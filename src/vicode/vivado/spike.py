"""Vi-Code M0: Thin end-to-end verification spike.

Proves that Vi-Code can detect Vivado, generate RTL, configure a Vivado Project Mode
project, execute synthesis, extract evidence, and persist structured Protocol 1 results.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from vicode.jobs import Layout, ProjectBusy, ProjectLock, build_layout, write_result
from vicode.results import Diagnostic, ExitCode, OperationResult
from vicode.vivado import discovery, messages, process, runner, tcl

PART_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

RE_LUT = re.compile(r"\|\s*(?:Slice LUTs\*?|LUT as Logic)\s*\|\s*(\d+)\s*\|")
RE_REG = re.compile(r"\|\s*(?:Slice Registers|Register as Flip Flop)\s*\|\s*(\d+)\s*\|")
RE_IOB = re.compile(r"\|\s*(?:Bonded IOB|IO)\s*\|\s*(\d+)\s*\|")
RE_BUFG = re.compile(r"\|\s*(?:BUFGCTRL|BUFG)\s*\|\s*(\d+)\s*\|")


def validate_part_format(part: str) -> bool:
    """True if ``part`` contains valid characters for an FPGA device part name."""
    return bool(part and PART_NAME_RE.fullmatch(part.strip()))


def generate_counter_rtl(width: int = 8) -> str:
    """Generate minimal synthesizable Verilog for an N-bit synchronous counter."""
    return f"""// Vi-Code M0 Thin Synthesis Spike - Minimal Synchronous Counter
`timescale 1ns / 1ps

module counter #(
    parameter WIDTH = {width}
) (
    input  wire             clk,
    input  wire             rst,
    input  wire             en,
    output reg  [WIDTH-1:0] count
);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= {width}'b0;
        end else if (en) begin
            count <= count + 1'b1;
        end
    end

endmodule
"""


def generate_synth_script(
    layout: Layout,
    rtl_path: Path,
    dcp_path: Path,
    rpt_path: Path,
    part: str,
    top: str = "counter",
    proj_dir: Path | None = None,
    proj_name: str = "spike_counter",
) -> str:
    """Generate Vivado Project Mode Tcl batch synthesis script.

    Guarantees:
    - Explicit variable initialization with safely quoted paths and parameters.
    - Integer-based catch block to prevent unhandled Tcl aborts.
    - Unconditional close_project attempt on both success and failure.
    - Explicit STATUS and PROGRESS verification of synth_1 run.
    """
    target_proj_dir = proj_dir or (layout.vivado / proj_name)
    lines = [
        f"set vicode_proj_name {tcl.quote(proj_name)}",
        f"set vicode_proj_dir {tcl.path(str(target_proj_dir))}",
        f"set vicode_part {tcl.quote(part)}",
        f"set vicode_top {tcl.quote(top)}",
        f"set vicode_rtl {tcl.path(str(rtl_path))}",
        f"set vicode_dcp_out {tcl.path(str(dcp_path))}",
        f"set vicode_rpt_out {tcl.path(str(rpt_path))}",
        "",
        "set vicode_code 0",
        "set vicode_msg \"\"",
        "",
        "set vicode_code [catch {",
        "    puts \"VICODE:m0_spike:begin\"",
        "",
        "    set vicode_part_matches [get_parts -quiet $vicode_part]",
        "    if {[llength $vicode_part_matches] == 0} {",
        "        error \"Target FPGA part '$vicode_part' is not available in this Vivado installation\"",
        "    }",
        "",
        "    create_project -force $vicode_proj_name $vicode_proj_dir -part $vicode_part",
        "    add_files -norecurse $vicode_rtl",
        "    set_property top $vicode_top [current_fileset]",
        "    update_compile_order -fileset sources_1",
        "",
        "    reset_run synth_1",
        "    launch_runs synth_1 -jobs 1",
        "    wait_on_run synth_1",
        "",
        "    set vicode_run_status [get_property STATUS [get_runs synth_1]]",
        "    set vicode_run_progress [get_property PROGRESS [get_runs synth_1]]",
        "    puts \"VICODE:run_status=$vicode_run_status\"",
        "    puts \"VICODE:run_progress=$vicode_run_progress\"",
        "",
        "    if {$vicode_run_status ne \"synth_design Complete!\" || $vicode_run_progress ne \"100%\"} {",
        "        error \"Synthesis run synth_1 did not complete successfully (STATUS='$vicode_run_status', PROGRESS='$vicode_run_progress')\"",
        "    }",
        "",
        "    open_run synth_1",
        "    report_utilization -file $vicode_rpt_out",
        "    write_checkpoint -force $vicode_dcp_out",
        "    puts \"VICODE:m0_spike:end\"",
        "} vicode_msg]",
        "",
        "catch { close_project }",
        "",
        "if {$vicode_code != 0} {",
        "    puts \"ERROR: $vicode_msg\"",
        "    exit $vicode_code",
        "}",
        "exit 0",
        "",
    ]
    return "\n".join(lines)


def parse_utilization_report(report_path: Path | str) -> dict[str, int]:
    """Parse resource utilization metrics from Vivado report_utilization output.

    Handles missing, empty, or malformed files gracefully without throwing.
    Never fabricates missing metric counts.
    """
    path = Path(report_path)
    if not path.is_file():
        return {}
    try:
        if path.stat().st_size == 0:
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    metrics: dict[str, int] = {}
    for line in text.splitlines():
        if "slice_luts" not in metrics:
            m = RE_LUT.search(line)
            if m:
                metrics["slice_luts"] = int(m.group(1))
        if "slice_registers" not in metrics:
            m = RE_REG.search(line)
            if m:
                metrics["slice_registers"] = int(m.group(1))
        if "bonded_iob" not in metrics:
            m = RE_IOB.search(line)
            if m:
                metrics["bonded_iob"] = int(m.group(1))
        if "bufg" not in metrics:
            m = RE_BUFG.search(line)
            if m:
                metrics["bufg"] = int(m.group(1))

    return metrics


def parse_spike_markers(lines: list[str]) -> dict[str, str]:
    """Extract VICODE:run_status=... and VICODE:run_progress=... markers from log lines."""
    markers: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if line.startswith("VICODE:") and "=" in line:
            key, _, val = line[len("VICODE:"):].partition("=")
            markers[key] = val
    return markers


def run_spike(
    root: Path | str,
    part: str | None = None,
    timeout: float = 600.0,
    vivado_bin: str | None = None,
    env: Mapping[str, str] | None = None,
    cancel: threading.Event | None = None,
) -> OperationResult:
    """Execute the M0 thin end-to-end verification spike.

    Guarantees:
    - Pre-run cleanup of spike output artifacts to prevent stale artifact reuse.
    - Primary evidence independence: process exit code, run properties, and fresh files.
    - Stale artifact detection via file mtime against run start time.
    - Fresh Protocol 1 result persisted on ALL paths (success and failure).
    """
    project_root = Path(root).resolve()
    layout = build_layout(project_root)
    layout.ensure()

    target_part = (part or "xc7a35tcpg236-1").strip()
    effective_env = dict(os.environ) if env is None else dict(env)

    result = OperationResult(
        operation="spike-synth",
        target_part=target_part,
        tool="vivado",
    )

    def fail(code: ExitCode, summary: str, details_update: dict[str, Any] | None = None) -> OperationResult:
        if details_update:
            result.details.update(details_update)
        result.finish(code, summary)
        try:
            write_result(layout, result)
        except OSError:
            pass
        return result

    # 1. Validate target part format
    if not validate_part_format(target_part):
        diag = Diagnostic(
            severity="error",
            message=f"target FPGA part '{target_part}' has invalid syntax or format",
            category="configuration",
        )
        result.diagnostics.append(diag)
        return fail(ExitCode.USAGE_OR_CONFIG, f"invalid target FPGA part: '{target_part}'")

    # 2. Dedicated spike file locations
    proj_dir = layout.vivado / "spike_counter"
    dcp_path = layout.artifacts / "spike_counter_synth.dcp"
    rpt_path = layout.reports / "spike_counter_utilization.rpt"
    rtl_dir = layout.root / "rtl"
    rtl_path = rtl_dir / "counter.v"
    tcl_log_path = layout.logs / "spike_synth.log"
    meta_result_path = layout.metadata / "spike-synth-result.json"

    # 3. Deterministic pre-run cleanup
    try:
        if dcp_path.exists():
            dcp_path.unlink()
        if rpt_path.exists():
            rpt_path.unlink()
        if proj_dir.exists():
            shutil.rmtree(proj_dir)
        if meta_result_path.exists():
            meta_result_path.unlink()
        if tcl_log_path.exists():
            tcl_log_path.unlink()
    except OSError as exc:
        diag = Diagnostic(severity="error", message=f"pre-run cleanup failed: {exc}", category="environment")
        result.diagnostics.append(diag)
        return fail(ExitCode.FAILED, f"cleanup failed before spike execution: {exc}")

    # 4. Generate RTL counter source
    try:
        rtl_dir.mkdir(parents=True, exist_ok=True)
        rtl_path.write_text(generate_counter_rtl(width=8), encoding="utf-8")
    except OSError as exc:
        diag = Diagnostic(severity="error", message=f"failed to write counter RTL: {exc}", category="environment")
        result.diagnostics.append(diag)
        return fail(ExitCode.FAILED, f"failed to write counter RTL: {exc}")

    # 5. Vivado Discovery
    selected_launcher: str | None = None
    if vivado_bin:
        inst = discovery.resolve_path(vivado_bin, process.IS_WINDOWS)
        if inst is None or not os.path.isfile(inst.launcher):
            diag = Diagnostic(
                severity="error",
                message=f"configured Vivado executable not found: {vivado_bin}",
                category="environment",
            )
            result.diagnostics.append(diag)
            return fail(ExitCode.ENVIRONMENT, f"configured Vivado executable not found: {vivado_bin}")
        selected_launcher = inst.launcher
        result.tool_version = inst.version
    else:
        installs = discovery.discover(effective_env, process.IS_WINDOWS, project_dir=project_root, cwd=os.getcwd())
        if not installs:
            diag = Diagnostic(severity="error", message="no Vivado installation found on system", category="environment")
            result.diagnostics.append(diag)
            return fail(ExitCode.ENVIRONMENT, "no Vivado installation found on system")
        selected_launcher = installs[0].launcher
        result.tool_version = installs[0].version

    # Batch validation on Windows
    if process.IS_WINDOWS and process.needs_batch_validation(selected_launcher):
        try:
            process.validate_batch_args([selected_launcher])
        except process.UnsafeArgument as exc:
            diag = Diagnostic(severity="error", message=str(exc), category="environment")
            result.diagnostics.append(diag)
            return fail(ExitCode.ENVIRONMENT, str(exc))

    # 6. Generate Project Mode Tcl Script
    script_text = generate_synth_script(
        layout=layout,
        rtl_path=rtl_path,
        dcp_path=dcp_path,
        rpt_path=rpt_path,
        part=target_part,
        top="counter",
        proj_dir=proj_dir,
        proj_name="spike_counter",
    )

    # 7. Acquire project lock
    lock = ProjectLock(layout.build, "spike-synth")
    try:
        lock.acquire()
    except ProjectBusy as exc:
        diag = Diagnostic(severity="error", message=str(exc), category="environment")
        result.diagnostics.append(diag)
        return fail(ExitCode.FAILED, str(exc))

    run_start_epoch = time.time()
    run: runner.TclRun | None = None
    try:
        run = runner.run_tcl(
            launcher=selected_launcher,
            script_text=script_text,
            layout=layout,
            name="spike_synth",
            env=effective_env,
            timeout=timeout,
            cancel=cancel,
        )
    except process.UnsafeArgument as exc:
        diag = Diagnostic(severity="error", message=str(exc), category="environment")
        result.diagnostics.append(diag)
        return fail(ExitCode.ENVIRONMENT, str(exc))
    except OSError as exc:
        diag = Diagnostic(severity="error", message=f"failed to spawn Vivado: {exc}", category="environment")
        result.diagnostics.append(diag)
        return fail(ExitCode.ENVIRONMENT, f"failed to spawn Vivado: {exc}")
    finally:
        try:
            lock.release()
        except OSError:
            pass

    if run is None:
        return fail(ExitCode.FAILED, "Vivado execution produced no run result")

    result.exit_code = run.outcome.exit_code
    if run.log.is_file():
        result.logs.append(str(run.log.resolve()))

    # Parse native Vivado diagnostics from output lines
    for diag in messages.parse_lines(run.lines):
        diag.category = "vivado"
        result.diagnostics.append(diag)

    # 8. Check process outcome
    if run.outcome.error:
        return fail(ExitCode.FAILED, f"Vivado failed to start: {run.outcome.error}")
    if run.outcome.cancelled:
        return fail(ExitCode.CANCELLED, "Vivado synthesis run was cancelled")
    if run.outcome.timed_out:
        return fail(ExitCode.CANCELLED, f"Vivado synthesis timed out after {timeout:g}s and was stopped")

    # Check for part error in lines or diagnostics
    log_text = "\n".join(run.lines)
    if "not available in this Vivado installation" in log_text or "Target FPGA part" in log_text:
        return fail(ExitCode.USAGE_OR_CONFIG, f"target FPGA part '{target_part}' is not available in Vivado installation")

    if run.outcome.exit_code != 0:
        return fail(ExitCode.FAILED, f"Vivado synthesis failed with exit code {run.outcome.exit_code}")

    # 9. Verify Primary Evidence
    markers = parse_spike_markers(run.lines)
    run_status = markers.get("run_status")
    run_progress = markers.get("run_progress")

    result.details["run_status"] = run_status
    result.details["run_progress"] = run_progress
    result.details["top_module"] = "counter"
    result.details["duration_seconds"] = round(run.outcome.duration_s, 3)

    if run_status != "synth_design Complete!" or run_progress != "100%":
        return fail(
            ExitCode.FAILED,
            f"synthesis run synth_1 did not complete successfully (STATUS='{run_status}', PROGRESS='{run_progress}')",
        )

    # Checkpoint verification
    if not dcp_path.is_file():
        return fail(ExitCode.FAILED, f"synthesis checkpoint was not generated: {dcp_path}")
    dcp_stat = dcp_path.stat()
    if dcp_stat.st_size == 0:
        return fail(ExitCode.FAILED, f"synthesis checkpoint is empty (0 bytes): {dcp_path}")
    if dcp_stat.st_mtime < run_start_epoch - 1.0:
        return fail(
            ExitCode.FAILED,
            f"synthesis checkpoint is stale (mtime {dcp_stat.st_mtime} < start {run_start_epoch}): {dcp_path}",
        )

    # Utilization report verification
    if not rpt_path.is_file():
        return fail(ExitCode.FAILED, f"synthesis utilization report was not generated: {rpt_path}")
    rpt_stat = rpt_path.stat()
    if rpt_stat.st_size == 0:
        return fail(ExitCode.FAILED, f"synthesis utilization report is empty (0 bytes): {rpt_path}")
    if rpt_stat.st_mtime < run_start_epoch - 1.0:
        return fail(
            ExitCode.FAILED,
            f"synthesis utilization report is stale (mtime {rpt_stat.st_mtime} < start {run_start_epoch}): {rpt_path}",
        )

    # 10. Parse utilization metrics
    util = parse_utilization_report(rpt_path)
    if util:
        result.details["utilization"] = util

    result.artifacts.append(str(dcp_path.resolve()))
    result.reports.append(str(rpt_path.resolve()))

    result.finish(
        ExitCode.OK,
        f"M0 counter synthesis spike completed successfully in {run.outcome.duration_s:.1f}s",
    )
    try:
        write_result(layout, result)
    except OSError as exc:
        diag = Diagnostic(severity="warning", message=f"could not write spike result record: {exc}", category="environment")
        result.diagnostics.append(diag)

    return result
