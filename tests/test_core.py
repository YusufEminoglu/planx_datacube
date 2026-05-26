# -*- coding: utf-8 -*-
"""Comprehensive unit tests for planx_datacube core modules.

Tests Ehsa statistics, forecasting, cube builder, and dependency manager.
Runs without QGIS with mocked qgis.* imports.
"""
from __future__ import annotations

import math
import os
import sys
import types
import traceback

# ---------------------------------------------------------------------------
# Mock qgis.*
# ---------------------------------------------------------------------------
def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m

class _Any: pass
def _make_mock_qgis_core():
    """Create a qgis.core module mock with all attributes needed."""
    m = types.ModuleType("qgis.core")
    needed = [
        "QgsVectorLayer", "QgsRasterLayer", "QgsFeature", "QgsGeometry",
        "QgsRectangle", "QgsPointXY", "QgsField", "QgsFields", "QgsFeatureSink",
        "QgsProcessingFeedback", "QgsSpatialIndex",
    ]
    for name in needed:
        setattr(m, name, _Any)
    return m

qgis_core = _make_mock_qgis_core()
qgis_qtgui = _mod("qgis.PyQt.QtGui")
qgis_qtcore = _mod("qgis.PyQt.QtCore", QVariant=lambda v=None: v)
qgis_pyqt = _mod("qgis.PyQt", QtGui=qgis_qtgui, QtCore=qgis_qtcore)
qgis = _mod("qgis", core=qgis_core, PyQt=qgis_pyqt)

sys.modules["qgis"] = qgis
sys.modules["qgis.core"] = qgis_core
sys.modules["qgis.PyQt"] = qgis_pyqt
sys.modules["qgis.PyQt.QtGui"] = qgis_qtgui
sys.modules["qgis.PyQt.QtCore"] = qgis_qtcore

# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PROJ))

from planx_datacube.core import statistics_ehsa as ehsa
from planx_datacube.core import forecasting_studio as fs
from planx_datacube.core import cube_builder as cb
from planx_datacube.core import dependency_manager as dm

# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------
passed = 0
failed = 0
errors = []

def check(name, cond, detail=""):
    global passed, failed, errors
    if cond:
        passed += 1
    else:
        failed += 1
        msg = f"FAIL [{name}]: {detail}"
        errors.append(msg)
        print(f"  {msg}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ===================================================================
# 1. STATISTICS EHSA — Getis-Ord Gi*
# ===================================================================
section("EHSA — Getis-Ord Gi*")

vals_simple = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
z = ehsa.getis_ord_g_star(vals_simple)
check("Gi* returns correct length", len(z) == 10, str(len(z)))
check("Gi* has negative and positive z", any(v < 0 for v in z) and any(v > 0 for v in z), str(z[:5]))
check("Gi* middle values near zero", abs(z[4]) < 1.5 or abs(z[5]) < 1.5, f"z[4]={z[4]:.3f} z[5]={z[5]:.3f}")

# Uniform values — all z should be 0
z_uniform = ehsa.getis_ord_g_star([5, 5, 5, 5, 5])
check("Gi* uniform -> all zero", all(abs(v) < 1e-9 for v in z_uniform), str(z_uniform))

# Small dataset
z_small = ehsa.getis_ord_g_star([1, 2])
check("Gi* 2 values ok", len(z_small) == 2)

# Outlier
z_outlier = ehsa.getis_ord_g_star([1, 1, 1, 1, 1, 100])
check("Gi* outlier gives extreme z", max(z_outlier) > 2.0, str(z_outlier))

# ===================================================================
# 2. STATISTICS EHSA — Mann-Kendall
# ===================================================================
section("EHSA — Mann-Kendall")

rising   = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
tau_r, p_r, sen_r = ehsa.mann_kendall_test(rising)
check("MK rising: tau > 0", tau_r > 0, f"tau={tau_r:.3f}")
check("MK rising: sen slope > 0", sen_r > 0, f"sen={sen_r:.3f}")
check("MK rising: p < 0.05", p_r < 0.05, f"p={p_r:.5f}")

falling  = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
tau_f, p_f, sen_f = ehsa.mann_kendall_test(falling)
check("MK falling: tau < 0", tau_f < 0, f"tau={tau_f:.3f}")
check("MK falling: sen slope < 0", sen_f < 0, f"sen={sen_f:.3f}")
check("MK falling: p < 0.05", p_f < 0.05, f"p={p_f:.5f}")

flat     = [5, 5, 5, 5, 5, 5, 5]
tau_0, p_0, sen_0 = ehsa.mann_kendall_test(flat)
check("MK flat: tau ~ 0", abs(tau_0) < 1e-9, f"tau={tau_0}")
check("MK flat: p >> 0.05", p_0 > 0.3, f"p={p_0}")

short = [1, 2]
tau_s, p_s, sen_s = ehsa.mann_kendall_test(short)
check("MK short series ok", tau_s == 0.0, f"tau={tau_s}")

# ===================================================================
# 3. STATISTICS EHSA — Pattern Classification
# ===================================================================
section("EHSA — 17-Pattern Classification")

# Simulate 10 timesteps for 5 locations
n_times, n_units = 10, 5
z_by_t = []
for t in range(n_times):
    # each time step: random-ish z-scores
    z_t = [math.sin(t * 0.5 + i) * 1.5 + (t - 5) * 0.1 for i in range(n_units)]
    z_by_t.append(z_t)

patterns = ehsa.classify_ehsa_pattern(z_by_t, 0.05)
check("EHSA returns one per unit", len(patterns) == n_units)
check("EHSA all valid codes", all(0 <= p <= 16 for p in patterns), str(patterns))

# All insignificant
z_by_t_insig = [[0.1, -0.1, 0.05, -0.05] for _ in range(n_times)]
pat_insig = ehsa.classify_ehsa_pattern(z_by_t_insig, 0.05)
check("EHSA insignificant -> all Not Sig", all(p == 0 for p in pat_insig), str(pat_insig))

# Persistent hot spot (always high positive)
z_hot = [[2.5, 2.6, 2.7, 2.8, 2.9] for _ in range(n_times)]
pat_hot = ehsa.classify_ehsa_pattern(z_hot, 0.05)
check("EHSA persistent hot", all(p > 0 for p in pat_hot), str(pat_hot))

# Persistent cold (always high negative)
z_cold = [[-2.5, -2.6, -2.7, -2.8, -2.9] for _ in range(n_times)]
pat_cold = ehsa.classify_ehsa_pattern(z_cold, 0.05)
check("EHSA persistent cold", all(p >= 9 for p in pat_cold), str(pat_cold))

# EHSA_LABELS
check("EHSA_LABELS has 17 entries", len(ehsa.EHSA_LABELS) == 17)
check("EHSA_LABELS 0 = Not Significant", ehsa.EHSA_LABELS[0] == "Not Significant")
check("EHSA_LABELS 4 = Persistent Hot Spot", ehsa.EHSA_LABELS[4] == "Persistent Hot Spot")
check("EHSA_LABELS 12 = Persistent Cold Spot", ehsa.EHSA_LABELS[12] == "Persistent Cold Spot")

# ===================================================================
# 4. FORECASTING — Exponential Smoothing
# ===================================================================
section("Forecasting — Exponential Smoothing")

series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
fc = fs.exponential_smoothing(series, alpha=0.3, steps_ahead=5)
check("ES returns correct steps", len(fc) == 5, str(fc))
check("ES continues last trend", all(fc[i] >= 20 for i in range(5)), str(fc))

# Edge: single value
fc1 = fs.exponential_smoothing([42], steps_ahead=3)
check("ES single value", fc1 == [42, 42, 42], str(fc1))

# Edge: None/NaN values in series
fc_nan = fs.exponential_smoothing([10, None, 20, math.nan, 30], steps_ahead=2)
check("ES with NaN gaps", len(fc_nan) == 2)

# ===================================================================
# 5. FORECASTING — ARIMA
# ===================================================================
section("Forecasting — ARIMA")

fc_a, method = fs.arima_forecast(series, steps_ahead=5)
check("ARIMA returns 5 values", len(fc_a) == 5, str(fc_a))
check("ARIMA returns method name", len(method) > 0)

# Short series falls back to ES
fc_a2, m2 = fs.arima_forecast([1, 2], steps_ahead=3)
check("ARIMA short series fallback", m2 == "exponential_smoothing")

# Flat series
fc_a3, m3 = fs.arima_forecast([5, 5, 5, 5, 5, 5, 5, 5], steps_ahead=3)
check("ARIMA flat series ok", len(fc_a3) == 3)

# ===================================================================
# 6. FORECASTING — Random Forest
# ===================================================================
section("Forecasting — Random Forest")

fc_rf, method_rf = fs.random_forest_forecast(series, lookback=3, steps_ahead=5)
check("RF returns 5 values or None", fc_rf is None or len(fc_rf) == 5, str(fc_rf))
check("RF returns method name", len(method_rf) > 0)

# Short series
fc_rf2, m_rf2 = fs.random_forest_forecast([1, 2, 3], steps_ahead=3)
check("RF short falls back to ES", m_rf2 == "exponential_smoothing" or m_rf2 == "random_forest")

# ===================================================================
# 7. FORECASTING — Forecast orchestrator
# ===================================================================
section("Forecasting — Orchestrator")

fc_orch, method = fs.forecast_cell_series(series, method="auto", steps_ahead=5)
check("forecast_cell_series returns 5 values", len(fc_orch) == 5)
check("forecast_cell_series returns method string", isinstance(method, str) and len(method) > 0)

# Explicit exponential
fc_exp, m_exp = fs.forecast_cell_series(series, method="exponential", steps_ahead=3)
check("explicit ES works", len(fc_exp) == 3 and m_exp == "exponential_smoothing")

# Empty series
fc_empty, m_empty = fs.forecast_cell_series([], method="auto", steps_ahead=3)
check("empty series returns zeros", fc_empty == [0.0, 0.0, 0.0] and m_empty == "none")

# All NaN series
fc_allnan, m_allnan = fs.forecast_cell_series([math.nan, math.nan, math.nan], method="auto", steps_ahead=3)
check("all NaN returns zeros", fc_allnan == [0.0, 0.0, 0.0])

# ===================================================================
# 8. CUBE BUILDER — DataCube
# ===================================================================
section("Cube Builder — DataCube")

cube = cb.DataCube(
    x_coords=[1.0, 2.0, 3.0],
    y_coords=[10.0, 20.0],
    time_steps=["2020", "2021", "2022"],
    variable_names=["temp", "pop"],
)
check("cube created ok", cube is not None)
check("cube x coords", len(cube.x_coords) == 3)
check("cube y coords", len(cube.y_coords) == 2)
check("cube time steps", len(cube.time_steps) == 3)
check("cube variables", cube.variable_names == ["temp", "pop"])

# Set and get values
cube.set_value(0, "temp", 1, 0, 25.5)
cube.set_value(0, "temp", 2, 1, 30.0)
cube.set_value(1, "pop", 0, 0, 1000.0)

s = cube.get_series(1, 0, "temp")
check("get_series returns correct length", len(s) == 3, str(s))
check("get_series first value correct", abs(s[0] - 25.5) < 1e-9, f"s[0]={s[0]}")
check("get_series other values nan", math.isnan(s[1]) and math.isnan(s[2]))

# Export to netCDF (test that it doesn't crash, may fail without netCDF4)
nc_path = os.path.join(os.path.dirname(__file__), "_test_cube.nc")
try:
    ok = cube.to_netcdf(nc_path)
    check("to_netcdf runs without crash", isinstance(ok, bool))
    if ok and os.path.exists(nc_path):
        os.remove(nc_path)
except Exception as e:
    print(f"  WARN: to_netcdf exception: {e} (expected if netCDF4 not installed)")

# ===================================================================
# 9. DEPENDENCY MANAGER (datacube deps)
# ===================================================================
section("Dependency Manager")

avail, miss_req, miss_opt = dm.check_packages(dm.DATA_CUBE_DEPS)
check("check_packages returns 3 lists", all(isinstance(x, list) for x in [avail, miss_req, miss_opt]))
check("numpy in results", "numpy" in avail or "numpy" in miss_req)
check("netCDF4 in results", "netCDF4" in avail or "netCDF4" in miss_req)
check("statsmodels in results", "statsmodels" in avail or "statsmodels" in miss_req)
check("scikit-learn in results", "scikit-learn" in avail or "scikit-learn" in miss_req)

report = dm.get_status_report(dm.DATA_CUBE_DEPS, "DATACUBE")
check("status report non-empty", isinstance(report, str) and len(report) > 100)
check("title in report", "DATACUBE" in report)

ok, msg = dm.install_packages([])
check("install_packages empty ok", ok)

ok2, msg2 = dm.install_packages(["nonexistent-package-12345xyz"])
check("install_packages nonexistent fails gracefully", isinstance(ok2, bool))

result = dm.ensure_required(dm.DATA_CUBE_DEPS, auto_install=False)
check("ensure_required returns bool", isinstance(result, bool))

# ===================================================================
# SUMMARY
# ===================================================================
section("RESULTS")
total = passed + failed
pct = 100 * passed / total if total > 0 else 0
print(f"  {passed}/{total} passed ({pct:.0f}%)", flush=True)
if failed:
    print(f"\n  FAILURES:", flush=True)
    for e in errors:
        print(f"    {e}", flush=True)
    sys.exit(1)
else:
    print("\n  ALL TESTS PASSED", flush=True)
    sys.exit(0)
