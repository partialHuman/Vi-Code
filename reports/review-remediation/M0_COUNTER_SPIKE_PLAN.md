# Vi-Code 0.1.0 — Milestone M0 Counter Synthesis Spike Plan

**Date:** 2026-11-02
**Target:** Close Milestone M0 Exit Criterion (Architecture Revision 1.1 §14)
**Requirement Ref:** R-05, R-08, VIC-REV-006
**Implementation Mode:** Isolated Thin Spike (does not prematurely implement CLI `vicode synth` for M3)

---

## 1. Objective and Scope

Architecture Revision 1.1 §14 defines the mandatory exit criterion for Milestone M0:
> **"Thin spike: doctor, init, synthesize the counter design, emit a structured JSON result"**
> **"Exit: basic Tcl batch execution succeeds; spike produces a structured result"**

In the initial 0.1.0 Foundation release, `vicode doctor` verified Vivado startup and device database querying, but synthesis was deferred (`vicode synth` returned exit code 5). This plan details the design, scripts, result schemas, and automated test harness required to deliver the counter synthesis spike, verify it against real Vivado 2018.2 on Windows 11, and close Milestone M0.

---

## 2. Counter RTL Design (`rtl/counter.v`)

A compact, synthesizable 8-bit binary counter with synchronous enable and asynchronous active-high reset. Testbench-free and target-independent:

```verilog
// Vi-Code Milestone M0 Synthesis Spike Design
`timescale 1ns / 1ps

module counter (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [7:0] count
);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= 8'h00;
        end else if (en) begin
            count <= count + 1'b1;
        end
    end

endmodule
```

### Resource Expectations (Zynq-7000 / `xc7z020clg400-1`)
* Target Part: `xc7z020clg400-1`
* LUT Utilization: ~8 LUTs (or combined CARRY4 + LUT)
* Register Utilization: 8 Flip-Flops (FDCE)
* I/O Buffers: 11 IBUF/OBUF pins

---

## 3. Vivado Project Mode Synthesis Workflow

In accordance with Architecture §11 and §14, synthesis is exercised through Vivado's standard Project Mode automation script:

### 3.1 Synthesis Tcl Script (`synth_spike.tcl`)

```tcl
# Vi-Code M0 Synthesis Spike Script
puts "VICODE:synth_begin"
set t0 [clock seconds]

# 1. Create in-memory or on-disk project
create_project -force spike_project ./spike_work -part [lindex $argv 0]

# 2. Add design sources
add_files -norecurse [lindex $argv 1]
set_property top counter [current_fileset]

# 3. Execute Synthesis
synth_design -top counter -part [lindex $argv 0]

# 4. Generate Reports and Artifacts
report_utilization -file utilization.rpt
write_checkpoint -force counter_synth.dcp

set t1 [clock seconds]
set elapsed [expr {$t1 - $t0}]

puts "VICODE:cells_luts=[get_property -quiet PRIMITIVE_COUNT [get_cells -hier -filter {PRIMITIVE_GROUP == CLB}]]"
puts "VICODE:synth_seconds=$elapsed"
puts "VICODE:synth_success=1"
puts "VICODE:synth_end"
```

---

## 4. Structured JSON Result Format (Protocol 1)

The synthesis spike produces an `OperationResult` conforming to Vi-Code protocol 1:

```json
{
  "protocol": 1,
  "vicode_version": "0.1.0",
  "operation": "spike.synth",
  "status": "succeeded",
  "tool": "vivado",
  "tool_version": "2018.2",
  "target_part": "xc7z020clg400-1",
  "started_at": "2026-11-02T12:00:00.000000Z",
  "finished_at": "2026-11-02T12:00:35.000000Z",
  "exit_code": 0,
  "vicode_exit_code": 0,
  "logs": [
    "build/logs/synth.log"
  ],
  "reports": [
    "build/reports/utilization.rpt"
  ],
  "artifacts": [
    "build/artifacts/counter_synth.dcp"
  ],
  "diagnostics": [
    {
      "severity": "info",
      "message": "synth_design completed successfully",
      "category": "vivado",
      "id": "Synth 8-256"
    }
  ],
  "summary": "synthesis of 'counter' succeeded in 32.4s (8 LUTs, 8 FFs)",
  "details": {
    "top_module": "counter",
    "target_part": "xc7z020clg400-1",
    "synthesis_seconds": 32.4,
    "utilization": {
      "luts": 8,
      "registers": 8,
      "io": 11
    },
    "artifacts_verified": {
      "checkpoint_exists": true,
      "report_exists": true
    }
  }
}
```

---

## 5. Success and Failure Evidence Criteria

In accordance with Vi-Code Design Principle NFR-02:
> **"A zero exit status alone is never accepted as proof that Vivado worked."**

### 5.1 Success Evidence Checklist
1. Vivado exit code is `0`.
2. Output contains both marker lines: `VICODE:synth_begin` and `VICODE:synth_end`.
3. Output contains `VICODE:synth_success=1`.
4. Synthesized design checkpoint `counter_synth.dcp` exists on disk and is non-empty (> 10 KB).
5. Utilization report `utilization.rpt` exists on disk, is non-empty, and reports non-zero cell counts.
6. Captured log contains Vivado completion marker `synth_design completed successfully`.

### 5.2 Failure Evidence Scenarios
* **Scenario A — RTL Syntax Error:**
  * Deliberate syntax error inserted into `counter.v` (e.g. missing semicolon or invalid token).
  * Vivado outputs `ERROR: [Synth 8-...]`.
  * Spike detects error, parses diagnostic `Synth 8-...`, verifies absence of completion markers.
  * Emits structured result with `status: "failed"`, `exit_code: 1`, and diagnostic list populated.
* **Scenario B — Invalid / Unresolvable Top Module:**
  * Top module set to non-existent module name `bogus_top`.
  * Vivado reports error.
  * Spike emits structured result with `status: "failed"`.

---

## 6. Test Plan

### 6.1 Fake-Vivado Contract Test (`tests/test_spike_synth.py`)
* Extend `tests/fakes/fake_vivado.py` to handle command argument `-source synth_spike.tcl`.
* When called with valid RTL, emit synthetic markers, generate dummy `utilization.rpt`, and return 0.
* When called with invalid RTL, emit simulated `ERROR: [Synth 8-27] syntax error` and return 1.
* Fully automated, runs offline on any OS in < 0.2s without requiring a Vivado license.

### 6.2 Real-Vivado Integration Test (`tests/test_integration_real_vivado.py`)
* Activated when `$env:VICODE_REAL_VIVADO="1"`.
* Invokes the spike against `D:\Xilinx\Vivado\2018.2\bin\vivado.bat` with part `xc7z020clg400-1`.
* Measures and asserts:
  * Synthesis completion time (~30–60 seconds).
  * DCP checkpoint creation.
  * Utilization report parsing.
  * Zero orphan processes remaining in Windows process table.
* Re-runs failure case (syntax error) and asserts structured error reporting.
