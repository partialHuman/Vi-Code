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
    for line in text.splitlines():
        line = line.strip()
        if line == 'puts "VICODE:begin"':
            out("VICODE:begin", log_fh)
        elif line == 'puts "VICODE:end"':
            out("VICODE:end", log_fh)
        elif "version -short" in line:
            out(f"VICODE:version={probe_version}", log_fh)
        elif "get_parts" in line:
            wanted = line.split("get_parts -quiet", 1)[1].split("]")[0].strip().replace("\\", "")
            out(f"VICODE:part_found={1 if wanted in parts else 0}", log_fh)
    if own.mode == "warn":
        out("WARNING: [Synth 8-3332] Sequential element (q_reg) is unused and will be removed. [C:/proj/rtl/top.sv:42]", log_fh)
        out("CRITICAL WARNING: [Vivado 12-4739] set_clock_groups: No valid object(s) found.", log_fh)
    out("INFO: [Common 17-206] Exiting Vivado.", log_fh)
    if log_fh:
        log_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
