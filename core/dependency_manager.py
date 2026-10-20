# -*- coding: utf-8 -*-
"""
Dependency Manager — Detect missing Python packages and guide installation.

Handles:
  1. Check which required/optional packages are available
  2. Report missing packages to the user
  3. Build the exact pip command for the user to run themselves

The plugin deliberately never executes pip itself: package installation is
the user's action, run in their own shell (OSGeo4W Shell on Windows), which
also keeps the plugin free of process-spawning code.

Used by both CartoLab and DataCube Lab as a shared sub-plugin pattern.
"""
from __future__ import annotations

import importlib
import sys
from typing import Dict, List, Tuple


# ── Package definitions ──────────────────────────────────────────────

# Format:  pypi_name : (import_name, required, purpose_description)

CARTO_LAB_DEPS: Dict[str, Tuple[str, bool, str]] = {
    "numpy": ("numpy", True, "Numerical array operations (GIC, cartogram, ridge maps)"),
    "matplotlib": ("matplotlib", False, "Colour ramp generation and chart previews"),
}

DATA_CUBE_DEPS: Dict[str, Tuple[str, bool, str]] = {
    "numpy": ("numpy", True, "Multi-dimensional array backbone for data cubes"),
    "netCDF4": ("netCDF4", False, "Read/write CF-style netCDF4 cubes and the Workbench loader"),
    "statsmodels": ("statsmodels", False, "ARIMA / SARIMAX models; exponential smoothing is the fallback"),
    "scikit-learn": ("sklearn", False, "Random Forest forecasting; exponential smoothing is the fallback"),
    "zarr": ("zarr", False, "Optional chunked Zarr export"),
    "matplotlib": ("matplotlib", False, "Chart preview visualization for the forecasting studio"),
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


def pip_install_command(package_names: List[str]) -> str:
    """
    Build the exact pip command for the current QGIS Python interpreter.

    The command is shown/copied for the user to run in their own shell
    (e.g. the OSGeo4W Shell); the plugin never executes it.
    """
    if not package_names:
        return ""
    return " ".join(
        [f'"{sys.executable}"', "-m", "pip", "install", "--upgrade", *package_names]
    )


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
        lines.append("\nMISSING (required — plugin may not work correctly):")
        for pkg in missing_req:
            _, _, purpose = deps[pkg]
            lines.append(f"  [!!] {pkg} — {purpose}")

    if missing_opt:
        lines.append("\nMISSING (optional — enhanced features unavailable):")
        for pkg in missing_opt:
            _, _, purpose = deps[pkg]
            lines.append(f"  [--] {pkg} — {purpose}")

    if not missing_req and not missing_opt:
        lines.append("\nAll dependencies satisfied.")

    return "\n".join(lines)
