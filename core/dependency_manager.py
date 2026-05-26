# -*- coding: utf-8 -*-
"""
Dependency Manager — Detect & install missing Python packages at runtime.

Handles the full lifecycle:
  1. Check which required/optional packages are available
  2. Report missing packages to the user
  3. Install them via pip subprocess (with user confirmation)
  4. Verify installation success

Used by both CartoLab and DataCube Lab as a shared sub-plugin pattern.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from typing import Dict, List, Tuple, Optional


# ── Package definitions ──────────────────────────────────────────────

# Format:  pypi_name : (import_name, required, purpose_description)

CARTO_LAB_DEPS: Dict[str, Tuple[str, bool, str]] = {
    "numpy": ("numpy", True, "Numerical array operations (GIC, cartogram, ridge maps)"),
    "matplotlib": ("matplotlib", False, "Colour ramp generation and chart previews"),
}

DATA_CUBE_DEPS: Dict[str, Tuple[str, bool, str]] = {
    "numpy": ("numpy", True, "Multi-dimensional array backbone for data cubes"),
    "netCDF4": ("netCDF4", True, "Read/write netCDF4 climate/earth-science data cubes"),
    "statsmodels": ("statsmodels", True, "ARIMA / SARIMAX time-series models"),
    "scikit-learn": ("sklearn", True, "Random Forest and ML-based time-series forecasting"),
    "xarray": ("xarray", False, "Labelled multi-dimensional array analysis"),
    "dask": ("dask", False, "Parallel out-of-core computation for large cubes"),
    "zarr": ("zarr", False, "Chunked compressed storage format for netCDF alternatives"),
}


# ── Core logic ───────────────────────────────────────────────────────

def check_packages(
    deps: Dict[str, Tuple[str, bool, str]]
) -> Tuple[List[str], List[str], List[str]]:
    """
    Check which packages are available.

    Returns (available, missing_required, missing_optional).
    Each entry is the PyPI package name.
    """
    available: List[str] = []
    missing_required: List[str] = []
    missing_optional: List[str] = []

    for pypi_name, (import_name, required, _purpose) in deps.items():
        try:
            importlib.import_module(import_name)
            available.append(pypi_name)
        except ImportError:
            if required:
                missing_required.append(pypi_name)
            else:
                missing_optional.append(pypi_name)

    return available, missing_required, missing_optional


def install_packages(package_names: List[str]) -> Tuple[bool, str]:
    """
    Install one or more packages via pip subprocess.

    Returns (success, output_message).
    """
    if not package_names:
        return True, "No packages to install."

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--upgrade", "--quiet",
        *package_names,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max
        )
        if result.returncode == 0:
            return True, f"Successfully installed: {', '.join(package_names)}"
        else:
            err = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown error"
            return False, f"pip install failed: {err}"
    except subprocess.TimeoutExpired:
        return False, "Installation timed out (5 minutes). Check your network connection."
    except FileNotFoundError:
        return False, "Python interpreter not found. Is Python in your PATH?"
    except Exception as exc:
        return False, f"Unexpected error: {exc}"


def get_status_report(
    deps: Dict[str, Tuple[str, bool, str]],
    title: str = "Dependency Status",
) -> str:
    """Build a human-readable status report."""
    available, missing_req, missing_opt = check_packages(deps)
    lines = [f"=== {title} ===", ""]

    if available:
        lines.append("Installed:")
        for pkg in available:
            _, _, purpose = deps[pkg]
            lines.append(f"  [OK] {pkg} — {purpose}")

    if missing_req:
        lines.append(f"\nMISSING (required — plugin may not work correctly):")
        for pkg in missing_req:
            _, _, purpose = deps[pkg]
            lines.append(f"  [!!] {pkg} — {purpose}")

    if missing_opt:
        lines.append(f"\nMISSING (optional — enhanced features unavailable):")
        for pkg in missing_opt:
            _, _, purpose = deps[pkg]
            lines.append(f"  [--] {pkg} — {purpose}")

    if not missing_req and not missing_opt:
        lines.append("\nAll dependencies satisfied.")

    return "\n".join(lines)


def ensure_required(
    deps: Dict[str, Tuple[str, bool, str]],
    auto_install: bool = False,
) -> bool:
    """
    Ensure all required packages are installed.

    If auto_install is True, installs missing packages without prompting.
    Returns True if all required packages are now available.
    """
    _, missing_req, _ = check_packages(deps)
    if not missing_req:
        return True
    if auto_install:
        ok, _ = install_packages(missing_req)
        if ok:
            _, still_missing, _ = check_packages(deps)
            return len(still_missing) == 0
        return False
    return False
