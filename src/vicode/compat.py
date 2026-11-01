"""Compatibility matrix: which Windows + Vivado combinations have actually been verified."""

from __future__ import annotations

import json
from importlib import resources

from vicode.platform_info import PlatformInfo


def load_matrix() -> dict:
    text = resources.files("vicode").joinpath("data/compat_matrix.json").read_text(encoding="utf-8")
    return json.loads(text)


def check(vivado_version: str | None, platform: PlatformInfo, matrix: dict | None = None) -> tuple[str, str]:
    """Return ``(status, message)`` where status is ``verified`` or ``untested``."""
    matrix = load_matrix() if matrix is None else matrix
    os_key = "windows-11" if platform.is_windows11 else platform.system
    if vivado_version:
        for entry in matrix.get("verified", []):
            if entry.get("os") == os_key and entry.get("vivado") == vivado_version:
                return "verified", f"{os_key} + Vivado {vivado_version} is in the verified matrix"
    shown = vivado_version or "unknown version"
    return (
        "untested",
        f"{os_key} + Vivado {shown} is not in the verified compatibility matrix yet "
        "(see docs/verification.md to record a verified combination)",
    )
