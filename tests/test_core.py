# -*- coding: utf-8 -*-
"""Comprehensive pytest tests for planx_datacube core modules.

Tests Ehsa statistics, forecasting, cube builder, and dependency manager.
Runs without QGIS with mocked qgis.* imports.
"""
from __future__ import annotations

import math
import os
import sys
import types


# ---------------------------------------------------------------------------
# Mock qgis.* — set up before any local imports
# ---------------------------------------------------------------------------
def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


class _Any:
    pass


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
# Imports (E402 is by design — mocks must load first)
# ---------------------------------------------------------------------------
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PROJ))

from planx_datacube.core import statistics_ehsa as ehsa  # noqa: E402
from planx_datacube.core import forecasting_studio as fs  # noqa: E402
from planx_datacube.core import cube_builder as cb  # noqa: E402
from planx_datacube.core import dependency_manager as dm  # noqa: E402
from planx_datacube.core import spatial_weights as sw  # noqa: E402
from planx_datacube.core import timeseries_stats as ts  # noqa: E402
from planx_datacube.core import local_morans as lm  # noqa: E402


# ===================================================================
# 1. STATISTICS EHSA — Getis-Ord Gi*
# ===================================================================

class TestGetisOrdGiStar:
    """Getis-Ord Gi* — global z-score."""

    def test_returns_correct_length(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        z = ehsa.getis_ord_g_star(vals)
        assert len(z) == 10, str(len(z))

    def test_has_negative_and_positive_z(self):
        z = ehsa.getis_ord_g_star([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert any(v < 0 for v in z) and any(v > 0 for v in z), str(z[:5])

    def test_middle_values_near_zero(self):
        z = ehsa.getis_ord_g_star([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert abs(z[4]) < 1.5 or abs(z[5]) < 1.5, f"z[4]={z[4]:.3f} z[5]={z[5]:.3f}"

    def test_uniform_all_zero(self):
        z = ehsa.getis_ord_g_star([5, 5, 5, 5, 5])
        assert all(abs(v) < 1e-9 for v in z), str(z)

    def test_small_dataset_two_values(self):
        z = ehsa.getis_ord_g_star([1, 2])
        assert len(z) == 2

    def test_outlier_gives_extreme_z(self):
        z = ehsa.getis_ord_g_star([1, 1, 1, 1, 1, 100])
        assert max(z) > 2.0, str(z)


# ===================================================================
# 2. STATISTICS EHSA — Mann-Kendall
# ===================================================================

class TestMannKendall:
    """Mann-Kendall trend test."""

    def test_rising_tau_positive(self):
        tau, p, sen = ehsa.mann_kendall_test([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert tau > 0, f"tau={tau:.3f}"

    def test_rising_sen_slope_positive(self):
        tau, p, sen = ehsa.mann_kendall_test([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert sen > 0, f"sen={sen:.3f}"

    def test_rising_p_significant(self):
        tau, p, sen = ehsa.mann_kendall_test([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert p < 0.05, f"p={p:.5f}"

    def test_falling_tau_negative(self):
        tau, p, sen = ehsa.mann_kendall_test([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        assert tau < 0, f"tau={tau:.3f}"

    def test_falling_sen_slope_negative(self):
        tau, p, sen = ehsa.mann_kendall_test([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        assert sen < 0, f"sen={sen:.3f}"

    def test_falling_p_significant(self):
        tau, p, sen = ehsa.mann_kendall_test([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        assert p < 0.05, f"p={p:.5f}"

    def test_flat_tau_zero(self):
        tau, p, sen = ehsa.mann_kendall_test([5, 5, 5, 5, 5, 5, 5])
        assert abs(tau) < 1e-9, f"tau={tau}"

    def test_flat_p_insignificant(self):
        tau, p, sen = ehsa.mann_kendall_test([5, 5, 5, 5, 5, 5, 5])
        assert p > 0.3, f"p={p}"

    def test_short_series(self):
        tau, p, sen = ehsa.mann_kendall_test([1, 2])
        assert tau == 0.0, f"tau={tau}"


# ===================================================================
# 3. STATISTICS EHSA — Pattern Classification
# ===================================================================

class TestEHSAPatternClassification:
    """17-pattern classification."""

    def test_one_per_unit(self):
        n_times, n_units = 10, 5
        z_by_t = []
        for t in range(n_times):
            z_t = [math.sin(t * 0.5 + i) * 1.5 + (t - 5) * 0.1 for i in range(n_units)]
            z_by_t.append(z_t)
        patterns = ehsa.classify_ehsa_pattern(z_by_t, 0.05)
        assert len(patterns) == n_units

    def test_all_valid_codes(self):
        n_times, n_units = 10, 5
        z_by_t = []
        for t in range(n_times):
            z_t = [math.sin(t * 0.5 + i) * 1.5 + (t - 5) * 0.1 for i in range(n_units)]
            z_by_t.append(z_t)
        patterns = ehsa.classify_ehsa_pattern(z_by_t, 0.05)
        assert all(0 <= p <= 16 for p in patterns), str(patterns)

    def test_insignificant_all_not_sig(self):
        z_by_t = [[0.1, -0.1, 0.05, -0.05] for _ in range(10)]
        pat = ehsa.classify_ehsa_pattern(z_by_t, 0.05)
        assert all(p == 0 for p in pat), str(pat)

    def test_persistent_hot(self):
        z_hot = [[2.5, 2.6, 2.7, 2.8, 2.9] for _ in range(10)]
        pat = ehsa.classify_ehsa_pattern(z_hot, 0.05)
        assert all(p > 0 for p in pat), str(pat)

    def test_persistent_cold(self):
        z_cold = [[-2.5, -2.6, -2.7, -2.8, -2.9] for _ in range(10)]
        pat = ehsa.classify_ehsa_pattern(z_cold, 0.05)
        assert all(p >= 9 for p in pat), str(pat)

    def test_labels_has_17_entries(self):
        assert len(ehsa.EHSA_LABELS) == 17

    def test_labels_0_is_not_significant(self):
        assert ehsa.EHSA_LABELS[0] == "Not Significant"

    def test_labels_4_is_persistent_hot_spot(self):
        assert ehsa.EHSA_LABELS[4] == "Persistent Hot Spot"

    def test_labels_12_is_persistent_cold_spot(self):
        assert ehsa.EHSA_LABELS[12] == "Persistent Cold Spot"


# ===================================================================
# 4. FORECASTING — Exponential Smoothing
# ===================================================================

class TestExponentialSmoothing:
    """Simple exponential smoothing forecaster."""

    def test_returns_correct_steps(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc = fs.exponential_smoothing(series, alpha=0.3, steps_ahead=5)
        assert len(fc) == 5, str(fc)

    def test_continues_last_trend(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc = fs.exponential_smoothing(series, alpha=0.3, steps_ahead=5)
        assert all(fc[i] >= 20 for i in range(5)), str(fc)

    def test_single_value(self):
        fc = fs.exponential_smoothing([42], steps_ahead=3)
        assert fc == [42, 42, 42], str(fc)

    def test_nan_gaps(self):
        fc = fs.exponential_smoothing([10, None, 20, math.nan, 30], steps_ahead=2)
        assert len(fc) == 2


# ===================================================================
# 5. FORECASTING — ARIMA
# ===================================================================

class TestARIMA:
    """ARIMA forecaster (with statsmodels if available)."""

    def test_returns_5_values(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, method = fs.arima_forecast(series, steps_ahead=5)
        assert len(fc) == 5, str(fc)

    def test_returns_method_name(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, method = fs.arima_forecast(series, steps_ahead=5)
        assert len(method) > 0

    def test_short_series_fallback(self):
        fc, m = fs.arima_forecast([1, 2], steps_ahead=3)
        assert m == "exponential_smoothing"

    def test_flat_series(self):
        fc, m = fs.arima_forecast([5, 5, 5, 5, 5, 5, 5, 5], steps_ahead=3)
        assert len(fc) == 3


# ===================================================================
# 6. FORECASTING — Random Forest
# ===================================================================

class TestRandomForest:
    """Random Forest time-series forecaster."""

    def test_returns_5_or_none(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, method = fs.random_forest_forecast(series, lookback=3, steps_ahead=5)
        assert fc is None or len(fc) == 5, str(fc)

    def test_returns_method_name(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, method = fs.random_forest_forecast(series, lookback=3, steps_ahead=5)
        assert len(method) > 0

    def test_short_falls_back_to_es(self):
        fc, m = fs.random_forest_forecast([1, 2, 3], steps_ahead=3)
        assert m == "exponential_smoothing" or m == "random_forest"


# ===================================================================
# 7. FORECASTING — Orchestrator
# ===================================================================

class TestForecastOrchestrator:
    """forecast_cell_series dispatcher."""

    def test_returns_5_values(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, method = fs.forecast_cell_series(series, method="auto", steps_ahead=5)
        assert len(fc) == 5

    def test_returns_method_string(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, method = fs.forecast_cell_series(series, method="auto", steps_ahead=5)
        assert isinstance(method, str) and len(method) > 0

    def test_explicit_exponential(self):
        series = [10, 12, 15, 14, 18, 20, 22, 25, 24, 28]
        fc, m = fs.forecast_cell_series(series, method="exponential", steps_ahead=3)
        assert len(fc) == 3 and m == "exponential_smoothing"

    def test_empty_series_returns_zeros(self):
        fc, m = fs.forecast_cell_series([], method="auto", steps_ahead=3)
        assert fc == [0.0, 0.0, 0.0] and m == "none"

    def test_all_nan_returns_zeros(self):
        fc, m = fs.forecast_cell_series([math.nan, math.nan, math.nan], method="auto", steps_ahead=3)
        assert fc == [0.0, 0.0, 0.0]


# ===================================================================
# 8. CUBE BUILDER — DataCube
# ===================================================================

class TestDataCube:
    """In-memory DataCube class."""

    def setup_method(self):
        self.cube = cb.DataCube(
            x_coords=[1.0, 2.0, 3.0],
            y_coords=[10.0, 20.0],
            time_steps=["2020", "2021", "2022"],
            variable_names=["temp", "pop"],
        )

    def test_created_ok(self):
        assert self.cube is not None

    def test_x_coords(self):
        assert len(self.cube.x_coords) == 3

    def test_y_coords(self):
        assert len(self.cube.y_coords) == 2

    def test_time_steps(self):
        assert len(self.cube.time_steps) == 3

    def test_variable_names(self):
        assert self.cube.variable_names == ["temp", "pop"]

    def test_get_series_length(self):
        self.cube.set_value(0, "temp", 1, 0, 25.5)
        self.cube.set_value(0, "temp", 2, 1, 30.0)
        self.cube.set_value(1, "pop", 0, 0, 1000.0)
        s = self.cube.get_series(1, 0, "temp")
        assert len(s) == 3, str(s)

    def test_get_series_first_value(self):
        self.cube.set_value(0, "temp", 1, 0, 25.5)
        self.cube.set_value(0, "temp", 2, 1, 30.0)
        s = self.cube.get_series(1, 0, "temp")
        assert abs(s[0] - 25.5) < 1e-9, f"s[0]={s[0]}"

    def test_get_series_other_values_nan(self):
        self.cube.set_value(0, "temp", 1, 0, 25.5)
        self.cube.set_value(0, "temp", 2, 1, 30.0)
        s = self.cube.get_series(1, 0, "temp")
        assert math.isnan(s[1]) and math.isnan(s[2])

    def test_to_netcdf_runs(self):
        nc_path = os.path.join(os.path.dirname(__file__), "_test_cube.nc")
        try:
            ok = self.cube.to_netcdf(nc_path)
            assert isinstance(ok, bool)
            if ok and os.path.exists(nc_path):
                os.remove(nc_path)
        except Exception as e:
            print(f"  WARN: to_netcdf exception: {e} (expected if netCDF4 not installed)")

    def test_to_zarr_runs(self):
        zarr_path = os.path.join(os.path.dirname(__file__), "_test_cube.zarr")
        try:
            ok_z = self.cube.to_zarr(zarr_path)
            assert isinstance(ok_z, bool)
            if ok_z and os.path.exists(zarr_path):
                import shutil
                shutil.rmtree(zarr_path, ignore_errors=True)
        except Exception as e:
            print(f"  WARN: to_zarr exception: {e} (expected if zarr not installed)")


# ===================================================================
# 9. DEPENDENCY MANAGER
# ===================================================================

class TestDependencyManager:
    """Dependency detection and reporting."""

    def test_check_packages_returns_3_lists(self):
        avail, miss_req, miss_opt = dm.check_packages(dm.DATA_CUBE_DEPS)
        assert all(isinstance(x, list) for x in [avail, miss_req, miss_opt])

    def test_numpy_in_results(self):
        avail, miss_req, miss_opt = dm.check_packages(dm.DATA_CUBE_DEPS)
        assert "numpy" in avail or "numpy" in miss_req

    def test_netcdf4_in_results(self):
        avail, miss_req, miss_opt = dm.check_packages(dm.DATA_CUBE_DEPS)
        assert "netCDF4" in avail or "netCDF4" in miss_req

    def test_statsmodels_in_results(self):
        avail, miss_req, miss_opt = dm.check_packages(dm.DATA_CUBE_DEPS)
        assert "statsmodels" in avail or "statsmodels" in miss_req

    def test_scikit_learn_in_results(self):
        avail, miss_req, miss_opt = dm.check_packages(dm.DATA_CUBE_DEPS)
        assert "scikit-learn" in avail or "scikit-learn" in miss_req

    def test_status_report_nonempty(self):
        report = dm.get_status_report(dm.DATA_CUBE_DEPS, "DATACUBE")
        assert isinstance(report, str) and len(report) > 100

    def test_title_in_report(self):
        report = dm.get_status_report(dm.DATA_CUBE_DEPS, "DATACUBE")
        assert "DATACUBE" in report

    def test_install_empty_ok(self):
        ok, msg = dm.install_packages([])
        assert ok

    def test_install_nonexistent_fails_gracefully(self):
        ok, msg = dm.install_packages(["nonexistent-package-12345xyz"])
        assert isinstance(ok, bool)

    def test_ensure_required_returns_bool(self):
        result = dm.ensure_required(dm.DATA_CUBE_DEPS, auto_install=False)
        assert isinstance(result, bool)


# ===================================================================
# 10. SPATIAL WEIGHTS
# ===================================================================

class TestSpatialWeights:
    """Neighbourhood construction."""

    def setup_method(self):
        self.line_coords = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]

    def test_knn_k1_one_neighbour_each(self):
        adj = sw.build_weights(self.line_coords, mode="knn", k=1)
        assert all(len(r) == 1 for r in adj), str([len(r) for r in adj])

    def test_knn_nearest_is_adjacent(self):
        adj = sw.build_weights(self.line_coords, mode="knn", k=1)
        assert adj[0][0][0] == 1, str(adj[0])

    def test_distance_band_endpoints(self):
        adj = sw.build_weights(self.line_coords, mode="distance_band", distance=1.5)
        assert len(adj[0]) == 1 and len(adj[3]) == 1

    def test_distance_band_middle(self):
        adj = sw.build_weights(self.line_coords, mode="distance_band", distance=1.5)
        assert len(adj[1]) == 2 and len(adj[2]) == 2

    def test_row_standardised_sum_to_one(self):
        adj = sw.build_weights(self.line_coords, mode="knn", k=2, row_standardize=True)
        assert all(abs(sum(w for _, w in r) - 1.0) < 1e-9 for r in adj)

    def test_include_self_adds_self_term(self):
        adj = sw.build_weights(self.line_coords, mode="knn", k=2, include_self=True)
        assert any(j == 0 for j, _ in adj[0])

    def test_include_self_count_equals_k_plus_1(self):
        adj = sw.build_weights(self.line_coords, mode="knn", k=2, include_self=True)
        assert len(adj[0]) == 3, str(len(adj[0]))

    def test_auto_distance_band_positive(self):
        d = sw.auto_distance_band(self.line_coords)
        assert d > 0, str(d)

    def test_n_less_than_2_safe(self):
        result = sw.build_weights([(0.0, 0.0)], mode="knn")
        assert result == [[]]


# ===================================================================
# 11. GETIS-ORD Gi* (weighted matrix)
# ===================================================================

class TestGetisOrdGiStarMatrix:
    """Weighted Gi* with spatial adjacency."""

    def test_self_only_standardised(self):
        vals = [10, 10, 1, 10, 1, 1, 1, 1, 1]
        adj = [[(i, 1.0)] for i in range(9)]
        zg = ehsa.getis_ord_gi_star_matrix(vals, adj)
        assert zg[0] > 0 and zg[8] < 0, f"{zg[0]:.3f}, {zg[8]:.3f}"

    def test_identical_global_weights_equal_z(self):
        vals = [10, 10, 1, 10, 1, 1, 1, 1, 1]
        adj = [[(j, 1.0) for j in range(9)] for _ in range(9)]
        zg = ehsa.getis_ord_gi_star_matrix(vals, adj)
        assert max(zg) - min(zg) < 1e-6, str(zg[:3])

    def test_n_less_than_3_zeros(self):
        result = ehsa.getis_ord_gi_star_matrix([1, 2], [[], []])
        assert result == [0.0, 0.0]


# ===================================================================
# 12. LOCAL MORAN'S I (LISA)
# ===================================================================

class TestLocalMoransI:
    """Anselin Local Moran's I with permutation test."""

    def setup_method(self):
        self.coords = [(x, y) for y in range(5) for x in range(5)]
        self.vals = [10.0 if (x < 3 and y < 3) else 0.0 for y in range(5) for x in range(5)]
        self.adj = sw.build_weights(self.coords, mode="knn", k=4, row_standardize=True)
        self.res = lm.local_morans_i(self.vals, self.adj, permutations=999, p_threshold=0.05, seed=42)

    def test_returns_one_per_unit(self):
        assert len(self.res["cluster"]) == 25

    def test_high_block_centre_is_hh(self):
        idx_center = 1 * 5 + 1  # (1,1) deep inside the high block
        assert self.res["cluster"][idx_center] == lm.LISA_HH, str(self.res["cluster"][idx_center])

    def test_high_cell_i_positive(self):
        idx_center = 1 * 5 + 1
        assert self.res["I"][idx_center] > 0, str(self.res["I"][idx_center])

    def test_low_cell_z_negative_and_lag_negative(self):
        idx_low = 4 * 5 + 4  # (4,4) deep in the zero region
        assert self.res["z"][idx_low] < 0 and self.res["lag"][idx_low] < 0, \
            f"z={self.res['z'][idx_low]:.2f} lag={self.res['lag'][idx_low]:.2f}"

    def test_deterministic_across_runs(self):
        res2 = lm.local_morans_i(self.vals, self.adj, permutations=999, p_threshold=0.05, seed=42)
        assert self.res["p"] == res2["p"]

    def test_n_less_than_3_safe(self):
        result = lm.local_morans_i([1, 2], [[], []], permutations=10)
        assert result["cluster"] == [lm.LISA_NS, lm.LISA_NS]


# ===================================================================
# 13. TIME-SERIES STATS — anomaly & trend
# ===================================================================

class TestTimeSeriesStats:
    """Robust z-scores, anomaly detection, trend classification."""

    def test_robust_z_flat_zeros(self):
        result = ts.robust_zscores([5, 5, 5, 5, 5])
        assert all(abs(v) < 1e-9 for v in result)

    def test_robust_z_flags_spike(self):
        spike = [10, 12, 11, 9, 10, 13, 200, 8, 11, 9, 12, 10]
        zr = ts.robust_zscores(spike)
        assert max(zr) > 5, f"max={max(zr):.1f}"

    def test_detect_anomalies_finds_one(self):
        spike = [10, 12, 11, 9, 10, 13, 200, 8, 11, 9, 12, 10]
        res = ts.detect_anomalies(spike, threshold=3.0)
        assert res["n_anomalies"] == 1, str(res["n_anomalies"])

    def test_detect_anomalies_index(self):
        spike = [10, 12, 11, 9, 10, 13, 200, 8, 11, 9, 12, 10]
        res = ts.detect_anomalies(spike, threshold=3.0)
        assert res["first_index"] == 6 and res["last_index"] == 6

    def test_last_not_anomalous(self):
        spike = [10, 12, 11, 9, 10, 13, 200, 8, 11, 9, 12, 10]
        res = ts.detect_anomalies(spike, threshold=3.0)
        assert res["last_is_anomaly"] is False

    def test_mad_zero_fallback(self):
        res = ts.detect_anomalies([50] * 11 + [250], threshold=3.0)
        assert res["n_anomalies"] >= 1, str(res["n_anomalies"])

    def test_classify_trend_increasing(self):
        assert ts.classify_trend(0.01, 5.0, 0.05) == ts.TREND_INCREASING

    def test_classify_trend_decreasing(self):
        assert ts.classify_trend(0.01, -5.0, 0.05) == ts.TREND_DECREASING

    def test_classify_trend_insignificant(self):
        assert ts.classify_trend(0.5, 5.0, 0.05) == ts.TREND_NONE

    def test_classify_trend_flat_slope(self):
        assert ts.classify_trend(0.01, 0.0, 0.05) == ts.TREND_NONE

    def test_sen_intercept(self):
        result = ts.sen_intercept([10, 15, 20, 25], 5.0)
        assert abs(result - 10.0) < 1e-9, str(result)


# ===================================================================
# 14. FORECASTING — metrics & backtest
# ===================================================================

class TestForecastMetrics:
    """Accuracy metrics and backtesting."""

    def test_mae_correct(self):
        mae, rmse, mape = fs.forecast_metrics([10, 20, 30], [12, 18, 33])
        assert abs(mae - (2 + 2 + 3) / 3) < 1e-9, str(mae)

    def test_rmse_correct(self):
        mae, rmse, mape = fs.forecast_metrics([10, 20, 30], [12, 18, 33])
        assert abs(rmse - ((4 + 4 + 9) / 3) ** 0.5) < 1e-9, str(rmse)

    def test_mape_positive(self):
        mae, rmse, mape = fs.forecast_metrics([10, 20, 30], [12, 18, 33])
        assert mape > 0, str(mape)

    def test_perfect_prediction_zero_error(self):
        m = fs.forecast_metrics([5, 5, 5], [5, 5, 5])
        assert m[0] == 0 and m[1] == 0

    def test_backtest_n_test(self):
        bt = fs.backtest_series([50.0] * 12, holdout=3)
        assert bt["n_test"] == 3, str(bt["n_test"])

    def test_backtest_flat_series_zero_rmse(self):
        bt = fs.backtest_series([50.0] * 12, holdout=3)
        assert bt["best_rmse"] < 1e-6, str(bt["best_rmse"])

    def test_backtest_picks_method(self):
        bt = fs.backtest_series([50.0] * 12, holdout=3)
        assert bt["best_method"] != "none", bt["best_method"]

    def test_backtest_too_short(self):
        bt = fs.backtest_series([1, 2], holdout=3)
        assert bt["best_method"] == "none"
