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
from planx_datacube.core import spatial_weights as sw
from planx_datacube.core import timeseries_stats as ts
from planx_datacube.core import local_morans as lm

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

# Export to Zarr (test that it doesn't crash, may fail without zarr)
zarr_path = os.path.join(os.path.dirname(__file__), "_test_cube.zarr")
try:
    ok_z = cube.to_zarr(zarr_path)
    check("to_zarr runs without crash", isinstance(ok_z, bool))
    if ok_z and os.path.exists(zarr_path):
        import shutil
        shutil.rmtree(zarr_path, ignore_errors=True)
except Exception as e:
    print(f"  WARN: to_zarr exception: {e} (expected if zarr not installed)")

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
# 10. SPATIAL WEIGHTS
# ===================================================================
section("Spatial Weights")

line_coords = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
adj_knn = sw.build_weights(line_coords, mode="knn", k=1)
check("knn k=1 -> 1 neighbour each", all(len(r) == 1 for r in adj_knn),
      str([len(r) for r in adj_knn]))
check("knn nearest is adjacent point", adj_knn[0][0][0] == 1, str(adj_knn[0]))

adj_db = sw.build_weights(line_coords, mode="distance_band", distance=1.5)
check("distance_band endpoints have 1 neighbour", len(adj_db[0]) == 1 and len(adj_db[3]) == 1)
check("distance_band middle has 2 neighbours", len(adj_db[1]) == 2 and len(adj_db[2]) == 2)

adj_rs = sw.build_weights(line_coords, mode="knn", k=2, row_standardize=True)
check("row-standardised weights sum to 1",
      all(abs(sum(w for _, w in r) - 1.0) < 1e-9 for r in adj_rs))

adj_self = sw.build_weights(line_coords, mode="knn", k=2, include_self=True)
check("include_self adds self term", any(j == 0 for j, _ in adj_self[0]))
check("include_self count = k+1", len(adj_self[0]) == 3, str(len(adj_self[0])))

d_auto = sw.auto_distance_band(line_coords)
check("auto distance band positive", d_auto > 0, str(d_auto))
check("build_weights n<2 safe", sw.build_weights([(0.0, 0.0)], mode="knn") == [[]])

# ===================================================================
# 11. GETIS-ORD Gi* (weighted matrix)
# ===================================================================
section("EHSA — Getis-Ord Gi* matrix")

vals_g = [10, 10, 1, 10, 1, 1, 1, 1, 1]
adj_self9 = [[(i, 1.0)] for i in range(9)]
zg = ehsa.getis_ord_gi_star_matrix(vals_g, adj_self9)
check("Gi* self-only = standardised z (high>0, low<0)",
      zg[0] > 0 and zg[8] < 0, f"{zg[0]:.3f}, {zg[8]:.3f}")

adj_global = [[(j, 1.0) for j in range(9)] for _ in range(9)]
zg2 = ehsa.getis_ord_gi_star_matrix(vals_g, adj_global)
check("Gi* identical global weights -> equal z", max(zg2) - min(zg2) < 1e-6, str(zg2[:3]))
check("Gi* matrix n<3 -> zeros", ehsa.getis_ord_gi_star_matrix([1, 2], [[], []]) == [0.0, 0.0])

# ===================================================================
# 12. LOCAL MORAN'S I
# ===================================================================
section("Local Moran's I (LISA)")

# 5x5 grid, top-left 3x3 block high (10), rest 0.
g_coords = [(x, y) for y in range(5) for x in range(5)]
g_vals = [10.0 if (x < 3 and y < 3) else 0.0 for y in range(5) for x in range(5)]
g_adj = sw.build_weights(g_coords, mode="knn", k=4, row_standardize=True)
lres = lm.local_morans_i(g_vals, g_adj, permutations=999, p_threshold=0.05, seed=42)
check("LISA returns one per unit", len(lres["cluster"]) == 25)
idx_center = 1 * 5 + 1                 # (1,1) deep inside the high block
idx_low = 4 * 5 + 4                    # (4,4) deep in the zero region
check("LISA high-block centre is High-High", lres["cluster"][idx_center] == lm.LISA_HH,
      str(lres["cluster"][idx_center]))
check("LISA high cell: I>0", lres["I"][idx_center] > 0, str(lres["I"][idx_center]))
check("LISA low cell: z<0 and lag<0",
      lres["z"][idx_low] < 0 and lres["lag"][idx_low] < 0,
      f"z={lres['z'][idx_low]:.2f} lag={lres['lag'][idx_low]:.2f}")

lres2 = lm.local_morans_i(g_vals, g_adj, permutations=999, p_threshold=0.05, seed=42)
check("LISA deterministic across runs", lres["p"] == lres2["p"])
check("LISA n<3 safe", lm.local_morans_i([1, 2], [[], []], permutations=10)["cluster"]
      == [lm.LISA_NS, lm.LISA_NS])

# ===================================================================
# 13. TIME-SERIES STATS — anomaly & trend
# ===================================================================
section("Time-Series Stats")

check("robust z flat -> zeros", all(abs(v) < 1e-9 for v in ts.robust_zscores([5, 5, 5, 5, 5])))
spike = [10, 12, 11, 9, 10, 13, 200, 8, 11, 9, 12, 10]
zr = ts.robust_zscores(spike)
check("robust z flags clear spike", max(zr) > 5, f"max={max(zr):.1f}")

res_a = ts.detect_anomalies(spike, threshold=3.0)
check("detect_anomalies finds 1", res_a["n_anomalies"] == 1, str(res_a["n_anomalies"]))
check("detect_anomalies index = 6", res_a["first_index"] == 6 and res_a["last_index"] == 6)
check("detect_anomalies last not anomalous", res_a["last_is_anomaly"] is False)

res_b = ts.detect_anomalies([50] * 11 + [250], threshold=3.0)
check("MAD-zero fallback still detects spike", res_b["n_anomalies"] >= 1, str(res_b["n_anomalies"]))

check("classify_trend increasing", ts.classify_trend(0.01, 5.0, 0.05) == ts.TREND_INCREASING)
check("classify_trend decreasing", ts.classify_trend(0.01, -5.0, 0.05) == ts.TREND_DECREASING)
check("classify_trend insignificant -> none", ts.classify_trend(0.5, 5.0, 0.05) == ts.TREND_NONE)
check("classify_trend flat slope -> none", ts.classify_trend(0.01, 0.0, 0.05) == ts.TREND_NONE)
check("sen_intercept correct", abs(ts.sen_intercept([10, 15, 20, 25], 5.0) - 10.0) < 1e-9,
      str(ts.sen_intercept([10, 15, 20, 25], 5.0)))

# ===================================================================
# 14. FORECASTING — metrics & backtest
# ===================================================================
section("Forecasting — metrics & backtest")

mae, rmse, mape = fs.forecast_metrics([10, 20, 30], [12, 18, 33])
check("MAE correct", abs(mae - (2 + 2 + 3) / 3) < 1e-9, str(mae))
check("RMSE correct", abs(rmse - ((4 + 4 + 9) / 3) ** 0.5) < 1e-9, str(rmse))
check("MAPE positive", mape > 0, str(mape))
m0 = fs.forecast_metrics([5, 5, 5], [5, 5, 5])
check("perfect prediction -> zero error", m0[0] == 0 and m0[1] == 0)

bt = fs.backtest_series([50.0] * 12, holdout=3)
check("backtest n_test = 3", bt["n_test"] == 3, str(bt["n_test"]))
check("backtest flat series -> ~0 RMSE", bt["best_rmse"] < 1e-6, str(bt["best_rmse"]))
check("backtest picks a method", bt["best_method"] != "none", bt["best_method"])
bt2 = fs.backtest_series([1, 2], holdout=3)
check("backtest too-short series -> none", bt2["best_method"] == "none")

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
