"""Compatibility matrix: which Windows + Vivado combinations have actually been verified."""

from __future__ import annotations

import copy
import json
from importlib import resources
from typing import Any

from vicode.platform_info import PlatformInfo

DEFAULT_MATRIX: dict[str, Any] = {
    "schema_version": 1,
    "note": "compatibility matrix fallback",
    "verified": [],
}


def parse_matrix(raw: str | None = None) -> tuple[dict[str, Any], str | None]:
    """Parse matrix JSON text or load package data; returns (matrix_dict, error_message)."""
    if raw is None:
        try:
            raw = resources.files("vicode").joinpath("data/compat_matrix.json").read_text(encoding="utf-8")
        except Exception as exc:
            return copy.deepcopy(DEFAULT_MATRIX), f"could not load compat_matrix.json: {exc}"
    try:
        data = json.loads(raw)
    except Exception as exc:
        return copy.deepcopy(DEFAULT_MATRIX), f"corrupt compatibility matrix JSON: {exc}"

    if not isinstance(data, dict):
        return copy.deepcopy(DEFAULT_MATRIX), f"compatibility matrix must be a JSON object, got {type(data).__name__}"
    if not isinstance(data.get("verified"), list):
        return copy.deepcopy(DEFAULT_MATRIX), "compatibility matrix missing 'verified' list"

    for i, entry in enumerate(data["verified"]):
        if not isinstance(entry, dict):
            return copy.deepcopy(DEFAULT_MATRIX), f"compatibility matrix entry {i} is not a JSON object"
        if not isinstance(entry.get("os"), str) or not entry.get("os", "").strip():
            return copy.deepcopy(DEFAULT_MATRIX), f"compatibility matrix entry {i} missing valid 'os' field"
        if not isinstance(entry.get("vivado"), str) or not entry.get("vivado", "").strip():
            return copy.deepcopy(DEFAULT_MATRIX), f"compatibility matrix entry {i} missing valid 'vivado' field"

    return data, None


def load_matrix(raw: str | None = None) -> dict[str, Any]:
    """Load compatibility matrix safely, returning a valid dictionary even on corrupt input."""
    matrix, _ = parse_matrix(raw)
    return matrix


def check(vivado_version: str | None, platform: PlatformInfo, matrix: Any = None) -> tuple[str, str]:
    """Return ``(status, message)`` where status is ``verified`` or ``untested``."""
    err: str | None = None
    if matrix is None:
        matrix_data, err = parse_matrix()
    elif isinstance(matrix, str):
        matrix_data, err = parse_matrix(matrix)
    elif isinstance(matrix, dict):
        if not isinstance(matrix.get("verified"), list):
            matrix_data, err = copy.deepcopy(DEFAULT_MATRIX), "compatibility matrix missing 'verified' list"
        else:
            matrix_data = matrix
            for i, entry in enumerate(matrix_data["verified"]):
                if not isinstance(entry, dict):
                    err = f"compatibility matrix entry {i} is not a JSON object"
                    matrix_data = copy.deepcopy(DEFAULT_MATRIX)
                    break
                if not isinstance(entry.get("os"), str) or not entry.get("os", "").strip():
                    err = f"compatibility matrix entry {i} missing valid 'os' field"
                    matrix_data = copy.deepcopy(DEFAULT_MATRIX)
                    break
                if not isinstance(entry.get("vivado"), str) or not entry.get("vivado", "").strip():
                    err = f"compatibility matrix entry {i} missing valid 'vivado' field"
                    matrix_data = copy.deepcopy(DEFAULT_MATRIX)
                    break
    else:
        matrix_data, err = copy.deepcopy(DEFAULT_MATRIX), f"matrix must be a dict, got {type(matrix).__name__}"

    os_key = "windows-11" if platform.is_windows11 else platform.system
    shown = vivado_version or "unknown version"

    if err:
        return (
            "untested",
            f"compatibility matrix issue ({err}); {os_key} + Vivado {shown} treated as untested",
        )

    verified_list = matrix_data.get("verified", [])
    if vivado_version:
        for entry in verified_list:
            if isinstance(entry, dict) and entry.get("os") == os_key and entry.get("vivado") == vivado_version:
                status_val = entry.get("status", "verified")
                if status_val == "verified":
                    return "verified", f"{os_key} + Vivado {vivado_version} is in the verified matrix"
                return "untested", f"{os_key} + Vivado {vivado_version} entry status is '{status_val}', not verified"

    return (
        "untested",
        f"{os_key} + Vivado {shown} is not in the verified compatibility matrix yet "
        "(see docs/verification.md to record a verified combination)",
    )
