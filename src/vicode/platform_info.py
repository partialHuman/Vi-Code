"""Host platform detection. Release 0.1 supports Windows 11 only (design Section 8)."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

WINDOWS_11_MIN_BUILD = 22000


@dataclass(frozen=True)
class PlatformInfo:
    system: str  # "windows" | "linux" | "macos" | other
    release: str
    windows_build: int | None
    is_windows: bool
    is_windows11: bool

    @property
    def label(self) -> str:
        if self.is_windows11:
            return f"Windows 11 (build {self.windows_build})"
        if self.is_windows:
            return f"Windows {self.release} (build {self.windows_build})"
        return f"{self.system} {self.release}"


def detect(system: str | None = None, windows_build: int | None = None, release: str | None = None) -> PlatformInfo:
    """Detect the host platform. Arguments exist so tests can simulate other hosts."""
    raw = (system or sys.platform).lower()
    if raw.startswith("win"):
        name = "windows"
    elif raw.startswith("linux"):
        name = "linux"
    elif raw == "darwin":
        name = "macos"
    else:
        name = raw
    build = windows_build
    if name == "windows" and build is None:
        getter = getattr(sys, "getwindowsversion", None)
        build = getter().build if getter else None
    rel = release if release is not None else platform.release()
    is_win = name == "windows"
    return PlatformInfo(name, rel, build, is_win, bool(is_win and build is not None and build >= WINDOWS_11_MIN_BUILD))
