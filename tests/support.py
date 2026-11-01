"""Shared helpers: build a fake Vivado install and run the CLI in-process."""
from __future__ import annotations

import contextlib
import io
import os
import shlex
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from vicode import cli

FAKE = Path(__file__).resolve().parent / "fakes" / "fake_vivado.py"
WINDOWS = os.name == "nt"


def make_fake_vivado(root: Path, version: str = "2023.2", mode: str = "ok", parts=("xc7z020clg400-1",),
                     probe_version: str | None = None, marker_dir: Path | None = None) -> Path:
    """Create ``<root>/Vivado/<version>/bin/vivado[.bat]`` and return the launcher path."""
    bin_dir = Path(root) / "Vivado" / version / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    args = ["--mode", mode, "--version", version, "--parts", ",".join(parts)]
    if probe_version:
        args += ["--probe-version", probe_version]
    if marker_dir:
        Path(marker_dir).mkdir(parents=True, exist_ok=True)
        args += ["--marker-dir", str(marker_dir)]
    if WINDOWS:
        launcher = bin_dir / "vivado.bat"
        quoted = " ".join(f'"{a}"' for a in args)
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{FAKE}" {quoted} %*\r\n', encoding="utf-8")
    else:
        launcher = bin_dir / "vivado"
        quoted = " ".join(shlex.quote(a) for a in args)
        launcher.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} {quoted} "$@"\n',
                            encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher


def run_cli(argv: list[str], cwd: Path | None = None, env: dict | None = None) -> tuple[int, str, str]:
    """Run ``vicode`` in-process; returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    old_cwd = os.getcwd()
    old_env = dict(os.environ)
    try:
        if cwd:
            os.chdir(cwd)
        if env:
            os.environ.update(env)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(argv)
            except SystemExit as exc:  # argparse exits for --version/--help/usage errors
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
    return int(code), out.getvalue(), err.getvalue()


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()


VALID_MANIFEST = """\
schema_version: 1
project:
  name: FlexRISC32
  top_module: flexrisc32_top
  hdl: SystemVerilog
target:
  part: xc7z020clg400-1
  board: pynq-z2
vivado:
  executable: auto
  mode: project
sources:
  rtl:
    - rtl/**/*.v
    - rtl/**/*.sv
  testbenches:
    - sim/**/*.sv
  constraints:
    - constraints/**/*.xdc
simulation:
  top: tb_flexrisc32
  simulator: xsim
build:
  jobs: 4
  run_synthesis: true
  run_implementation: true
  generate_bitstream: false
"""
