"""Locate Vivado installations (design Section 8.3).

Discovery order: the explicitly configured path, ``XILINX_VIVADO``, ``PATH``, then known
default install roots (newest version first). Every installation found is reported.
The default roots are educated starting points and must be confirmed in milestone M0.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

VERSION_RE = re.compile(r"^(20\d{2})\.(\d)(?:\.\d+)?$")


@dataclass(frozen=True)
class Installation:
    launcher: str  # full path to vivado / vivado.bat
    version: str | None  # taken from the install directory name, if recognisable
    source: str  # configured | XILINX_VIVADO | PATH | default-root | extra-root

    @property
    def root(self) -> str:
        """Install directory (the folder that contains ``bin``)."""
        return os.path.dirname(os.path.dirname(self.launcher))


def launcher_names(windows: bool) -> tuple[str, ...]:
    return ("vivado.bat",) if windows else ("vivado",)


def version_from_path(path: str) -> str | None:
    """Return the version-looking directory name (e.g. ``2023.2``) closest to the file."""
    parts = re.split(r"[\\/]+", path)
    for part in reversed(parts):
        if VERSION_RE.match(part):
            return part
    return None


def version_key(version: str | None) -> tuple[int, int]:
    match = VERSION_RE.match(version or "")
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def default_roots(windows: bool, env: Mapping[str, str]) -> list[str]:
    """Known default install parent directories for the host family."""
    if windows:
        system_drive = env.get("SystemDrive") or env.get("SYSTEMDRIVE") or "C:"
        drives: list[str] = []
        for drive in (system_drive, "C:", "D:", "E:"):
            if drive.upper() not in [d.upper() for d in drives]:
                drives.append(drive)
        roots: list[str] = []
        for drive in drives:
            for vendor in ("Xilinx", "AMD"):
                roots.append(f"{drive}\\{vendor}\\Vivado")  # <root>\<version>\bin
                roots.append(f"{drive}\\{vendor}")  # <root>\<version>\Vivado\bin
        return roots
    home = env.get("HOME") or os.path.expanduser("~")
    return [
        "/tools/Xilinx/Vivado", "/opt/Xilinx/Vivado", "/tools/Xilinx", "/opt/Xilinx",
        os.path.join(home, "Xilinx", "Vivado"), os.path.join(home, "Xilinx"),
    ]


def _scan_root(root: str, names: tuple[str, ...], source: str) -> list[Installation]:
    found: list[Installation] = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return found
    for entry in entries:
        base = os.path.join(root, entry)
        for rel in (("bin",), ("Vivado", "bin")):
            for name in names:
                candidate = os.path.join(base, *rel, name)
                if os.path.isfile(candidate):
                    found.append(Installation(candidate, version_from_path(base), source))
    return found


def resolve_path(path: str, windows: bool) -> Installation | None:
    """Resolve a user-supplied path: a launcher file, an install directory or its ``bin``."""
    names = launcher_names(windows)
    if os.path.isfile(path):
        return Installation(path, version_from_path(path), "configured")
    if os.path.isdir(path):
        for rel in ((), ("bin",)):
            for name in names:
                candidate = os.path.join(path, *rel, name)
                if os.path.isfile(candidate):
                    return Installation(candidate, version_from_path(path), "configured")
    return None


def discover(
    env: Mapping[str, str],
    windows: bool,
    configured: str | None = None,
    extra_roots: Iterable[str] = (),
    which: Callable[[str], str | None] = shutil.which,
    include_default_roots: bool = True,
) -> list[Installation]:
    """Return installations in priority order, de-duplicated by real path."""
    names = launcher_names(windows)
    ordered: list[Installation] = []

    if configured:
        inst = resolve_path(configured, windows)
        if inst:
            ordered.append(inst)

    xilinx_vivado = env.get("XILINX_VIVADO")
    if xilinx_vivado:
        for name in names:
            candidate = os.path.join(xilinx_vivado, "bin", name)
            if os.path.isfile(candidate):
                ordered.append(Installation(candidate, version_from_path(xilinx_vivado), "XILINX_VIVADO"))

    for name in names:
        hit = which(name)
        if hit and os.path.isfile(hit):
            ordered.append(Installation(hit, version_from_path(os.path.dirname(os.path.dirname(hit))), "PATH"))

    scanned: list[Installation] = []
    for root in extra_roots:
        scanned += _scan_root(root, names, "extra-root")
    if include_default_roots:
        for root in default_roots(windows, env):
            scanned += _scan_root(root, names, "default-root")
    scanned.sort(key=lambda i: version_key(i.version), reverse=True)
    ordered += scanned

    seen: set[str] = set()
    unique: list[Installation] = []
    for inst in ordered:
        key = os.path.normcase(os.path.realpath(inst.launcher))
        if key not in seen:
            seen.add(key)
            unique.append(inst)
    return unique
