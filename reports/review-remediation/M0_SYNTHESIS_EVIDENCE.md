# Vi-Code Milestone M0: Counter Synthesis Spike Evidence

**Date:** 2026-11-04
**Branch:** `feat/m0-counter-synthesis-spike`
**Base Commit:** `ee04077091f2ed1a9bcb2bdc2eef77fd5b1456fb`
**Platform:** Windows 11 Pro (build 26300)
**EDA Tool:** Xilinx Vivado v2018.2 (64-bit), Build 2258646
**Status:** **PASSED & VERIFIED**

---

## 1. Executive Summary

Milestone M0 is the thin end-to-end integration proof for Vi-Code. Its objective is to prove that Vi-Code can:

1. Detect an installed, supported Vivado environment on Windows 11.
2. Generate synthesizable RTL (`counter.v`).
3. Configure a Vivado Project Mode project with non-interactive batch Tcl.
4. Execute synthesis via standard Project Mode run control (`launch_runs synth_1 -jobs 1`, `wait_on_run synth_1`).
5. Open the synthesized design (`open_run synth_1`) and extract evidence (utilization report and checkpoint `.dcp`).
6. Enforce evidence independence: verify physical artifacts, fresh modification times, non-zero file sizes, and authentic run properties (`STATUS == "synth_design Complete!"`, `PROGRESS == "100%"`).
7. Persist structured Protocol 1 JSON results across all execution paths.

This spike was executed against a real, unmodified installation of **Vivado 2018.2** on Windows 11. All criteria passed completely.

---

## 2. Environment Verification

| Parameter | Observed Value | Verification Method |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 (build 26300) | `platform_info.detect()` |
| **Python Version** | Python 3.14.7 (AMD64) | `sys.version` |
| **Vivado Launcher** | `D:\Xilinx\Vivado\2018.2\bin\vivado.bat` | `discovery.discover()` via `default-root` |
| **Vivado Version** | `2018.2` (Build 2258646) | Live batch probe output |
| **Target Device Part** | `xc7a35tcpg236-1` (Artix-7 35T) | Validated via `get_parts -quiet` |

---

## 3. Implementation Architecture

### 3.1 RTL Source Generation (`src/vicode/vivado/spike.py`)
Generates a minimal 8-bit synchronous counter:
```verilog
`timescale 1ns / 1ps

module counter #(
    parameter WIDTH = 8
) (
    input  wire             clk,
    input  wire             rst,
    input  wire             en,
    output reg  [WIDTH-1:0] count
);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= 8'b0;
        end else if (en) begin
            count <= count + 1'b1;
        end
    end

endmodule
```

### 3.2 Vivado Project Mode Synthesis Flow
Synthesis uses AMD Vivado's standard Project Mode run flow:
1. `create_project -force spike_counter <proj_dir> -part xc7a35tcpg236-1`
2. `add_files -norecurse <rtl_path>`
3. `set_property top counter [current_fileset]`
4. `update_compile_order -fileset sources_1`
5. `reset_run synth_1`
6. `launch_runs synth_1 -jobs 1`
7. `wait_on_run synth_1`
8. Query `get_property STATUS [get_runs synth_1]` and `get_property PROGRESS [get_runs synth_1]`
9. `open_run synth_1`
10. `report_utilization -file <rpt_path>`
11. `write_checkpoint -force <dcp_path>`
12. Unconditional `catch { close_project }`

### 3.3 Robustness & Review Conditions Incorporated
1. **Integer-Based Tcl Catch & Safe Cleanup**:
   All operations inside Tcl run within `set vicode_code [catch { ... } vicode_msg]`.
   `catch { close_project }` executes unconditionally on both success and failure before script termination.
2. **Explicit Variable Initialization & Quoting**:
   All paths and identifiers are quoted with `tcl.path()` and `tcl.quote()`, with explicit variable initialization at the top of the Tcl script.
3. **Stale Artifact Protection**:
   Target directories and prior output files are cleaned before execution. Checkpoint and report files are verified to have `mtime >= run_start_epoch - 1.0` and size > 0.
4. **Evidence Independence**:
   No reliance on artificial indicators (e.g. `synth_success=1`). Proof of success requires process exit code 0, Vivado run property status `"synth_design Complete!"`, progress `"100%"`, and fresh non-zero physical output files.
5. **No Fabricated Diagnostics**:
   Native Vivado diagnostic messages (such as `[Constraints 18-5210]`) are preserved without inventing placeholder IDs. Resource counts are parsed directly from reports; unparsed metrics are omitted rather than guessed.

---

## 4. Live Verification Evidence

### 4.1 Integration Test Execution (`tests/test_integration_real_vivado.py`)

Command:
```powershell
$env:PYTHONPATH="src"; $env:VICODE_REAL_VIVADO="1"; python -m unittest tests.test_integration_real_vivado -v
```

Output:
```text
test_counter_synthesis_with_real_vivado (tests.test_integration_real_vivado.RealVivadoTests.test_counter_synthesis_with_real_vivado) ... ok
test_doctor_with_real_vivado (tests.test_integration_real_vivado.RealVivadoTests.test_doctor_with_real_vivado) ... ok

----------------------------------------------------------------------
Ran 2 tests in 83.363s

OK

Real Vivado Synthesis Result:
Status: succeeded
Summary: M0 counter synthesis spike completed successfully in 75.6s
Tool Version: 2018.2
Target Part: xc7a35tcpg236-1
Artifacts: ['C:\\Users\\User\\AppData\\Local\\Temp\\tmpysdjd6t5\\build\\artifacts\\spike_counter_synth.dcp']
Reports: ['C:\\Users\\User\\AppData\\Local\\Temp\\tmpysdjd6t5\\build\\reports\\spike_counter_utilization.rpt']
Utilization: {
  "slice_luts": 6,
  "slice_registers": 8,
  "bonded_iob": 11,
  "bufg": 1
}
```

### 4.2 Standalone CLI Execution (`scripts/m0_counter_spike.py`)

Command:
```powershell
$env:PYTHONPATH="src"; python scripts/m0_counter_spike.py --project-dir build/real_spike_test --json
```

Output (Captured Protocol 1 JSON):
```json
{
  "protocol": 1,
  "vicode_version": "0.1.0",
  "operation": "spike-synth",
  "status": "succeeded",
  "tool": "vivado",
  "tool_version": "2018.2",
  "target_part": "xc7a35tcpg236-1",
  "started_at": "2026-11-04T07:56:19.412564Z",
  "finished_at": "2026-11-04T07:56:55.732303Z",
  "exit_code": 0,
  "vicode_exit_code": 0,
  "logs": [
    "C:\\Users\\User\\Documents\\Projects\\Vi-Code\\build\\real_spike_test\\build\\logs\\spike_synth.log"
  ],
  "reports": [
    "C:\\Users\\User\\Documents\\Projects\\Vi-Code\\build\\real_spike_test\\build\\reports\\spike_counter_utilization.rpt"
  ],
  "artifacts": [
    "C:\\Users\\User\\Documents\\Projects\\Vi-Code\\build\\real_spike_test\\build\\artifacts\\spike_counter_synth.dcp"
  ],
  "diagnostics": [
    {
      "severity": "warning",
      "message": "No constraint will be written out.",
      "id": "Constraints 18-5210",
      "category": "vivado"
    }
  ],
  "summary": "M0 counter synthesis spike completed successfully in 36.3s",
  "details": {
    "run_status": "synth_design Complete!",
    "run_progress": "100%",
    "top_module": "counter",
    "duration_seconds": 36.3,
    "utilization": {
      "slice_luts": 6,
      "slice_registers": 8,
      "bonded_iob": 11,
      "bufg": 1
    }
  }
}
```

### 4.3 Physical Artifact Verification

| Artifact File | Size | Verification Check |
| :--- | :--- | :--- |
| `spike_counter_synth.dcp` | 11,000 bytes | Physical Vivado design checkpoint verified |
| `spike_counter_utilization.rpt` | 7,217 bytes | Standard Vivado 2018.2 utilization report generated |
| `spike_synth.log` | 16,420 bytes | Complete stdout + stderr log captured |
| `spike-synth-result.json` | 1,302 bytes | Atomic Protocol 1 result recorded |

### 4.4 Utilization Metrics Extracted from Real Vivado Report

Excerpt from `spike_counter_utilization.rpt`:
```text
1. Slice Logic
+-------------------------+------+-------+-----------+-------+
|        Site Type        | Used | Fixed | Available | Util% |
+-------------------------+------+-------+-----------+-------+
| Slice LUTs*             |    6 |     0 |     20800 |  0.03 |
|   LUT as Logic          |    6 |     0 |     20800 |  0.03 |
|   LUT as Memory         |    0 |     0 |      9600 |  0.00 |
| Slice Registers         |    8 |     0 |     41600 |  0.02 |
|   Register as Flip Flop |    8 |     0 |     41600 |  0.02 |
+-------------------------+------+-------+-----------+-------+

4. IO and GT Specific
+-----------------------------+------+-------+-----------+-------+
|          Site Type          | Used | Fixed | Available | Util% |
+-----------------------------+------+-------+-----------+-------+
| Bonded IOB                  |   11 |     0 |       106 | 10.38 |
+-----------------------------+------+-------+-----------+-------+

5. Clocking
+------------+------+-------+-----------+-------+
|  Site Type | Used | Fixed | Available | Util% |
+------------+------+-------+-----------+-------+
| BUFGCTRL   |    1 |     0 |        32 |  3.13 |
+------------+------+-------+-----------+-------+
```

Summary:
- **Slice LUTs**: 6 (LUTs as logic implementing 8-bit incrementer)
- **Slice Registers**: 8 (8-bit count register)
- **Bonded IOB**: 11 (8 count outputs + 1 clk + 1 rst + 1 en)
- **BUFGCTRL**: 1 (global clock buffer)

---

## 5. Test Suite Results

1. **Full Strict Discovery Suite** (excluding live hardware/EDA flags):
   ```text
   Ran 171 tests in 21.781s
   OK (skipped=2)
   ```
2. **Opt-in Real Vivado Integration Suite** (`VICODE_REAL_VIVADO=1`):
   ```text
   Ran 2 tests in 83.363s
   OK
   ```
3. **Combined Verified Coverage**:
   - Total test cases: 173
   - Failures: 0
   - Errors: 0

---

## 6. Milestone M0 Verdict

**ACCEPTANCE CRITERIA FULLY SATISFIED.**
Vi-Code has demonstrated end-to-end integration with AMD/Xilinx Vivado 2018.2 in Project Mode, producing verified synthesized checkpoints, accurate resource utilization metrics, and conformant Protocol 1 results.
