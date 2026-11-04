"""A stand-in for ``vivado`` used by the contract tests (design Section 12.4).

It understands the small subset of the command line that Vi-Code uses and emulates
different behaviours (``--mode``). It never starts real EDA software.
"""
import argparse
import os
import subprocess
import sys
import time


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--mode", default="ok")
    ap.add_argument("--version", default="2023.2")
    ap.add_argument("--probe-version", default=None)
    ap.add_argument("--parts", default="")
    ap.add_argument("--marker-dir", default=None)
    own, rest = ap.parse_known_args(argv)

    opts = {}
    i = 0
    while i < len(rest):
        if rest[i] in ("-mode", "-source", "-log", "-journal", "-tempDir") and i + 1 < len(rest):
            opts[rest[i]] = rest[i + 1]
            i += 2
        else:
            opts[rest[i]] = True
            i += 1

    if own.marker_dir:
        with open(os.path.join(own.marker_dir, "invoked.txt"), "a", encoding="utf-8") as fh:
            fh.write(" ".join(rest) + "\n")
        with open(os.path.join(own.marker_dir, "env_seen.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(os.environ)))

    if "-version" in opts:
        print(f"Vivado v{own.version} (64-bit)")
        return 0

    log = opts.get("-log")
    probe_version = own.probe_version or own.version
    parts = [p for p in own.parts.split(",") if p]

    def out(line, log_fh=None):
        print(line, flush=True)
        if log_fh:
            log_fh.write(line + "\n")

    log_fh = open(log, "w", encoding="utf-8") if log else None
    out(f"****** Vivado v{probe_version} (64-bit)", log_fh)
    script = opts.get("-source")
    out(f"source {script}", log_fh)

    if own.mode == "tcl_error":
        print("ERROR: [Common 17-39] 'version' failed due to earlier errors.", file=sys.stderr, flush=True)
        return 1
    if own.mode == "silent_success":
        out("INFO: [Common 17-206] Exiting Vivado.", log_fh)
        return 0
    if own.mode == "hang":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(os.path.join(os.path.dirname(log), "child.pid"), "w", encoding="utf-8") as fh:
            fh.write(str(child.pid))
        time.sleep(120)
        return 0

    text = open(script, encoding="utf-8").read() if script else ""
    vicode_part = None
    vicode_dcp_out = None
    vicode_rpt_out = None

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("set vicode_part "):
            vicode_part = line.split(None, 2)[-1].strip('"\'')
        elif line.startswith("set vicode_dcp_out "):
            vicode_dcp_out = line.split(None, 2)[-1].strip('"\'')
        elif line.startswith("set vicode_rpt_out "):
            vicode_rpt_out = line.split(None, 2)[-1].strip('"\'')
        elif line == 'puts "VICODE:begin"':
            out("VICODE:begin", log_fh)
        elif line == 'puts "VICODE:end"':
            out("VICODE:end", log_fh)
        elif line == 'puts "VICODE:m0_spike:begin"':
            out("VICODE:m0_spike:begin", log_fh)
        elif line == 'puts "VICODE:m0_spike:end"':
            out("VICODE:m0_spike:end", log_fh)
        elif "version -short" in line:
            out(f"VICODE:version={probe_version}", log_fh)
        elif "get_parts" in line:
            if "vicode_part" in line:
                if (own.mode == "spike_part_unavailable") or (parts and vicode_part and vicode_part not in parts):
                    out(f"ERROR: Target FPGA part '{vicode_part}' is not available in this Vivado installation", log_fh)
                    if log_fh:
                        log_fh.close()
                    return 1
            else:
                wanted = line.split("get_parts -quiet", 1)[1].split("]")[0].strip().replace("\\", "")
                out(f"VICODE:part_found={1 if wanted in parts else 0}", log_fh)

    if own.mode == "spike_part_unavailable":
        out(f"ERROR: Target FPGA part '{vicode_part or 'unknown'}' is not available in this Vivado installation", log_fh)
        if log_fh:
            log_fh.close()
        return 1

    if own.mode == "spike_fail_run":
        out("VICODE:run_status=synth_design Failed!", log_fh)
        out("VICODE:run_progress=50%", log_fh)
        out("ERROR: [Synth 8-2357] syntax error in counter.v", log_fh)
        if log_fh:
            log_fh.close()
        return 1

    if "launch_runs synth_1" in text or own.mode.startswith("spike_"):
        if own.mode == "spike_incomplete_status":
            out("VICODE:run_status=synth_design Failed!", log_fh)
            out("VICODE:run_progress=100%", log_fh)
        elif own.mode == "spike_incomplete_progress":
            out("VICODE:run_status=synth_design Complete!", log_fh)
            out("VICODE:run_progress=80%", log_fh)
        else:
            out("VICODE:run_status=synth_design Complete!", log_fh)
            out("VICODE:run_progress=100%", log_fh)
            out("INFO: [Synth 8-638] synthesizing module 'counter'", log_fh)
            out("INFO: [Common 17-349] Got license for feature 'Synthesis' and/or device 'xc7a35t'", log_fh)

            if vicode_dcp_out and own.mode != "spike_missing_dcp":
                dcp_path = os.path.normpath(vicode_dcp_out)
                os.makedirs(os.path.dirname(dcp_path), exist_ok=True)
                if own.mode == "spike_zero_byte_dcp":
                    with open(dcp_path, "wb"):
                        pass
                else:
                    with open(dcp_path, "wb") as f:
                        f.write(b"PK\x03\x04fake_dcp_bytes")
                    if own.mode == "spike_stale_dcp":
                        stale_time = time.time() - 3600
                        os.utime(dcp_path, (stale_time, stale_time))

            if vicode_rpt_out and own.mode != "spike_missing_rpt":
                rpt_path = os.path.normpath(vicode_rpt_out)
                os.makedirs(os.path.dirname(rpt_path), exist_ok=True)
                if own.mode == "spike_zero_byte_rpt":
                    with open(rpt_path, "w", encoding="utf-8"):
                        pass
                else:
                    sample_rpt = (
                        "Copyright 1986-2018 Xilinx, Inc. All Rights Reserved.\n"
                        "----------------------------------------------------\n"
                        "| Tool Version : Vivado v.2018.2 (win64) Build 2258646\n"
                        "| Date         : Wed Nov  4 12:00:00 2026\n"
                        "| Design       : counter\n"
                        "| Device       : 7a35tcpg236-1\n"
                        "| Design State : Synthesized\n"
                        "----------------------------------------------------\n\n"
                        "Utilization Design Information\n\n"
                        "1. Slice Logic\n"
                        "+-------------------------+------+-------+-----------+-------+\n"
                        "|        Site Type        | Used | Fixed | Available | Util% |\n"
                        "+-------------------------+------+-------+-----------+-------+\n"
                        "| Slice LUTs*             |    8 |     0 |     20800 |  0.04 |\n"
                        "|   LUT as Logic          |    8 |     0 |     20800 |  0.04 |\n"
                        "| Slice Registers         |    8 |     0 |     41600 |  0.02 |\n"
                        "|   Register as Flip Flop |    8 |     0 |     41600 |  0.02 |\n"
                        "+-------------------------+------+-------+-----------+-------+\n\n"
                        "4. IO and GT Specific\n"
                        "+----------------+------+-------+-----------+-------+\n"
                        "|    Site Type   | Used | Fixed | Available | Util% |\n"
                        "+----------------+------+-------+-----------+-------+\n"
                        "| Bonded IOB     |   10 |     0 |       106 |  9.43 |\n"
                        "+----------------+------+-------+-----------+-------+\n\n"
                        "5. Clocking\n"
                        "+----------------+------+-------+-----------+-------+\n"
                        "|    Site Type   | Used | Fixed | Available | Util% |\n"
                        "+----------------+------+-------+-----------+-------+\n"
                        "| BUFGCTRL       |    1 |     0 |        32 |  3.13 |\n"
                        "+----------------+------+-------+-----------+-------+\n"
                    )
                    with open(rpt_path, "w", encoding="utf-8") as f:
                        f.write(sample_rpt)
                    if own.mode == "spike_stale_rpt":
                        stale_time = time.time() - 3600
                        os.utime(rpt_path, (stale_time, stale_time))

    if own.mode == "warn":
        out("WARNING: [Synth 8-3332] Sequential element (q_reg) is unused and will be removed. [C:/proj/rtl/top.sv:42]", log_fh)
        out("CRITICAL WARNING: [Vivado 12-4739] set_clock_groups: No valid object(s) found.", log_fh)
    out("INFO: [Common 17-206] Exiting Vivado.", log_fh)
    if log_fh:
        log_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
