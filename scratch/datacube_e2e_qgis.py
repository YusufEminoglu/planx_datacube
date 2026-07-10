# -*- coding: utf-8 -*-
"""End-to-end headless QGIS test for planx_datacube — all 8 Processing algorithms.

Run with OSGeo4W:
  QGIS 3.44: C:/OSGeo4W/bin/python-qgis-ltr.bat scratch/datacube_e2e_qgis.py
  QGIS 4:    C:/OSGeo4W/bin/python-qgis.bat    scratch/datacube_e2e_qgis.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import QgsApplication  # noqa: E402

qgs = QgsApplication([], False)
qgs.initQgis()

# Insert OSGeo4W processing plugin path FIRST so QGIS's 'processing' module
# is not shadowed by planx_datacube/processing/ (CWD is in sys.path by default).
_plugins_dir = os.path.join(QgsApplication.prefixPath(), "python", "plugins")
if os.path.isdir(_plugins_dir):
    sys.path.insert(0, _plugins_dir)
sys.path.append(r"C:\Users\YE\PyCharmMiscProject\qgis_plugins")

import processing  # noqa: E402
from processing.core.Processing import Processing  # noqa: E402

Processing.initialize()

from planx_datacube.processing.datacube_provider import DataCubeProvider  # noqa: E402

provider = DataCubeProvider()
QgsApplication.processingRegistry().addProvider(provider)

# ---- Regression guard: pin algorithm count ----
algo_count = len(list(provider.algorithms()))
assert algo_count == 8, f"expected 8 algorithms, got {algo_count}"  # nosec B101
print(f"Algorithm count pin: {algo_count} (PASS)")

fails = []


def check(cond, label):
    print(f"  [{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)


# ============================================================================
# Helper: build a synthetic long-format panel layer in memory.
# Creates N locations x T time steps with known patterns:
#   - loc_0..loc_3: rising/falling trend
#   - loc_4..loc_5: hot spots (high values, spatial cluster)
#   - loc_6..loc_7: cold spots (low values, spatial cluster)
#   - Grid: 3 cols x 3 rows, loc_id = "loc_{row}_{col}"
# ============================================================================
from qgis.core import (  # noqa: E402
    QgsFeature, QgsField, QgsFields, QgsGeometry,
    QgsPointXY, QgsRectangle, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402


def _make_panel_layer(n_locations=9, n_times=10, with_anomaly=False):
    """Return a memory polygon layer in long-format panel.

    Creates a 3x3 grid of square polygons. The grid layout means
    loc_0 (top-left) and loc_1 (top-centre) are spatial neighbours,
    producing meaningful Gi* and LISA clusters.

    Value pattern per location:
      loc_0, loc_1: hot cluster (values ~50-80, rising)
      loc_2:        medium-warm (~30-45)
      loc_3, loc_4: baseline (~15-25, noise)
      loc_5:        medium-cool (~5-15)
      loc_6, loc_7: cold cluster (values ~0-5, flat)
      loc_8:        baseline with a spike at t=8 if with_anomaly=True
    """
    fields = QgsFields()
    fields.append(QgsField("loc_id", QVariant.String))
    fields.append(QgsField("time_step", QVariant.Int))
    fields.append(QgsField("value", QVariant.Double))

    layer = QgsVectorLayer(
        "Polygon?crs=EPSG:32635&field=loc_id:string&field=time_step:integer&field=value:double",
        "synthetic_panel", "memory")
    dp = layer.dataProvider()
    dp.addAttributes(fields)
    layer.updateFields()

    layer.startEditing()

    # Build per-location base values and trends
    # loc_id = f"loc_{r}_{c}" for row in 0..2, col in 0..2
    loc_configs = [
        # (row, col, base, trend_per_step, label)
        (0, 0, 50.0,  3.0,  "hot_rising"),      # loc_0_0 -> loc 0
        (0, 1, 55.0,  2.5,  "hot_rising2"),     # loc_0_1 -> loc 1
        (0, 2, 30.0,  1.5,  "warm"),            # loc_0_2 -> loc 2
        (1, 0, 15.0,  0.5,  "baseline1"),       # loc_1_0 -> loc 3
        (1, 1, 25.0,  0.0,  "baseline2"),       # loc_1_1 -> loc 4
        (1, 2, 10.0, -0.5,  "cool"),            # loc_1_2 -> loc 5
        (2, 0,  5.0,  0.0,  "cold1"),           # loc_2_0 -> loc 6
        (2, 1,  2.0,  0.1,  "cold2"),           # loc_2_1 -> loc 7
        (2, 2, 20.0,  0.2,  "baseline_anom"),   # loc_2_2 -> loc 8
    ]

    feats = []
    for idx, (row, col, base, trend, label) in enumerate(loc_configs):
        loc_id = f"loc_{row}_{col}"
        # centroid of each grid cell (100m cells)
        cx = 500000 + col * 100 + 50
        cy = 4500000 + row * 100 + 50
        for t in range(n_times):
            # Add noise
            import random
            rng = random.Random(idx * 1000 + t)  # nosec B311
            noise = rng.gauss(0, 2.0)
            value = base + trend * t + noise

            # For loc_8, add a strong anomaly at t=8
            if with_anomaly and idx == 8 and t == 8:
                value = 200.0

            feat = QgsFeature(fields)
            geom = QgsGeometry.fromRect(
                QgsRectangle(cx - 50, cy - 50, cx + 50, cy + 50))
            feat.setGeometry(geom)
            feat.setAttributes([loc_id, t, round(value, 6)])
            feats.append(feat)

    dp.addFeatures(feats)
    layer.commitChanges()
    return layer


def _make_points_layer(n_points=30, n_times=3):
    """Return a memory point layer for space-time cube aggregation."""
    fields = QgsFields()
    fields.append(QgsField("event_time", QVariant.Int))
    fields.append(QgsField("pop", QVariant.Double))

    layer = QgsVectorLayer(
        "Point?crs=EPSG:32635&field=event_time:integer&field=pop:double",
        "synthetic_events", "memory")
    dp = layer.dataProvider()
    dp.addAttributes(fields)
    layer.updateFields()

    import random
    rng = random.Random(42)  # nosec B311

    feats = []
    layer.startEditing()
    for i in range(n_points):
        for t in range(n_times):
            feat = QgsFeature(fields)
            x = 500000 + rng.uniform(0, 500)
            y = 4500000 + rng.uniform(0, 500)
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feat.setAttributes([t, rng.uniform(10, 100)])
            feats.append(feat)
    dp.addFeatures(feats)
    layer.commitChanges()
    return layer


def _make_vector_time_layers(n_layers=3):
    """Return list of polygon layers (one per time step) for cube builder."""
    layers = []
    import random
    rng = random.Random(99)  # nosec B311
    for t in range(n_layers):
        layer = QgsVectorLayer(
            "Polygon?crs=EPSG:32635&field=pop:double",
            f"time_{t}", "memory")
        dp = layer.dataProvider()
        layer.startEditing()
        feats = []
        for row in range(3):
            for col in range(3):
                feat = QgsFeature()
                cx = 500000 + col * 100 + 50
                cy = 4500000 + row * 100 + 50
                geom = QgsGeometry.fromRect(
                    QgsRectangle(cx - 50, cy - 50, cx + 50, cy + 50))
                feat.setGeometry(geom)
                feat.setAttributes([rng.uniform(10, 80)])
                feats.append(feat)
        dp.addFeatures(feats)
        layer.commitChanges()
        layers.append(layer)
    return layers


# ============================================================================
# 1. Create Data Cube (vector input)
# ============================================================================
print("\n=== 1/8: create_data_cube (vector input) ===")
vec_layers = _make_vector_time_layers(3)
res1 = processing.run(
    "planx_datacube:create_data_cube",
    {
        "LAYERS": vec_layers,
        "FIELD": "pop",
        "GRID_RES": 100.0,
        "CUBE_TYPE": 0,  # vector
        "OUTPUT_NC": None,
        "OUTPUT_ZARR": None,
        "OUTPUT_INFO": "TEMPORARY_OUTPUT",
    },
)
info = res1["OUTPUT_INFO"]
check(info is not None and "Data cube built" in str(info), f"cube summary: {str(info)[:120]}")
check("X cells:" in str(info), "summary reports X cells")
check("Time steps:" in str(info), "summary reports time steps")


# ============================================================================
# 2. Space-Time Cube Aggregation
# ============================================================================
print("\n=== 2/8: space_time_cube ===")
pts = _make_points_layer(30, 3)
res2 = processing.run(
    "planx_datacube:space_time_cube",
    {
        "INPUT": pts,
        "TIME_FIELD": "event_time",
        "VALUE_FIELD": "pop",
        "AGG": 0,           # count
        "GRID_SIZE": 100.0,
        "TIME_STEP": 0.0,
        "DROP_EMPTY": True,
        "OUTPUT": "TEMPORARY_OUTPUT",
        "OUTPUT_NC": None,
    },
)
layer2 = res2["OUTPUT"]
if isinstance(layer2, str):
    layer2 = QgsVectorLayer(layer2, "stc", "ogr")
check(layer2.isValid(), "space_time_cube output valid")
check(layer2.featureCount() > 0, f"panel has rows (got {layer2.featureCount()})")
# Verify panel schema
fld_names = [f.name() for f in layer2.fields()]
for req in ["cell_id", "time_step", "value", "count"]:
    check(req in fld_names, f"field '{req}' present")


# ============================================================================
# 3. Emerging Hot Spot Analysis (EHSA)
# ============================================================================
print("\n=== 3/8: emerging_hot_spot_analysis ===")
panel = _make_panel_layer(9, 10)
res3 = processing.run(
    "planx_datacube:emerging_hot_spot_analysis",
    {
        "INPUT": panel,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "P_THRESHOLD": 0.05,
        "SPATIAL_REL": 1,   # fixed distance band
        "DISTANCE": 200.0,  # covers neighbours in a 3x3 100m grid
        "N_NEIGHBORS": 8,
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer3 = res3["OUTPUT"]
if isinstance(layer3, str):
    layer3 = QgsVectorLayer(layer3, "ehsa", "ogr")
check(layer3.isValid(), "EHSA output valid")
check(layer3.featureCount() == 9, f"9 locations (got {layer3.featureCount()})")
# Verify key fields
ehsa_fields = {f.name() for f in layer3.fields()}
for req in ["ehsa_code", "ehsa_label", "mk_tau", "mk_p_value", "mk_slope"]:
    check(req in ehsa_fields, f"EHSA field '{req}' present")

# Check that at least some locations got classified (non-zero ehsa_code)
codes = []
for f in layer3.getFeatures():
    codes.append(f["ehsa_code"])
check(any(c != 0 for c in codes), f"some locations classified non-zero (codes: {codes})")
check(0 <= min(codes) <= max(codes) <= 16, f"all codes in 0..16 range (min={min(codes)}, max={max(codes)})")

# Verify mk_tau sign matches expectation: loc_0_0 (hot_rising) should have tau > 0
loc_0_0 = next((f for f in layer3.getFeatures() if f["location_id"] == "loc_0_0"), None)
if loc_0_0:
    check(loc_0_0["mk_tau"] > 0, f"hot rising loc_0_0 mk_tau > 0 (got {loc_0_0['mk_tau']:.4f})")


# ============================================================================
# 4. Local Moran's I (LISA)
# ============================================================================
print("\n=== 4/8: local_morans_i ===")
res4 = processing.run(
    "planx_datacube:local_morans_i",
    {
        "INPUT": panel,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "TIME_AGG": 0,      # mean
        "SPATIAL_REL": 0,   # distance band
        "DISTANCE": 200.0,
        "N_NEIGHBORS": 8,
        "PERMUTATIONS": 99,
        "P_THRESHOLD": 0.05,
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer4 = res4["OUTPUT"]
if isinstance(layer4, str):
    layer4 = QgsVectorLayer(layer4, "lisa", "ogr")
check(layer4.isValid(), "LISA output valid")
check(layer4.featureCount() == 9, f"9 locations (got {layer4.featureCount()})")
lisa_fields = {f.name() for f in layer4.fields()}
for req in ["cluster_code", "cluster", "local_i", "z_score", "p_value"]:
    check(req in lisa_fields, f"LISA field '{req}' present")

# Check cluster codes are in valid range (0-4)
codes4 = [f["cluster_code"] for f in layer4.getFeatures()]
check(all(0 <= c <= 4 for c in codes4), f"all cluster codes in 0..4 (got {codes4})")


# ============================================================================
# 5. Temporal Trend Analysis
# ============================================================================
print("\n=== 5/8: temporal_trend ===")
res5 = processing.run(
    "planx_datacube:temporal_trend",
    {
        "INPUT": panel,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "P_THRESHOLD": 0.05,
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer5 = res5["OUTPUT"]
if isinstance(layer5, str):
    layer5 = QgsVectorLayer(layer5, "trend", "ogr")
check(layer5.isValid(), "Trend output valid")
check(layer5.featureCount() == 9, f"9 locations (got {layer5.featureCount()})")
trend_fields = {f.name() for f in layer5.fields()}
for req in ["trend_code", "trend", "mk_tau", "sen_slope", "sen_intercept"]:
    check(req in trend_fields, f"Trend field '{req}' present")

# loc_0_0 (hot_rising) should show increasing trend
loc_0_0_t = next((f for f in layer5.getFeatures() if f["location_id"] == "loc_0_0"), None)
if loc_0_0_t:
    check(loc_0_0_t["sen_slope"] > 0, f"rising loc_0_0 sen_slope > 0 (got {loc_0_0_t['sen_slope']:.4f})")

# loc_6 (cold1, flat) should have slope near 0
loc_2_0_t = next((f for f in layer5.getFeatures() if f["location_id"] == "loc_2_0"), None)
if loc_2_0_t:
    check(abs(loc_2_0_t["sen_slope"]) < 1.0, f"flat loc_2_0 slope near 0 (got {loc_2_0_t['sen_slope']:.4f})")


# ============================================================================
# 6. Temporal Anomaly Detection
# ============================================================================
print("\n=== 6/8: temporal_anomaly ===")
panel_anom = _make_panel_layer(9, 10, with_anomaly=True)
res6 = processing.run(
    "planx_datacube:temporal_anomaly",
    {
        "INPUT": panel_anom,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "THRESHOLD": 3.0,
        "METHOD": 0,        # robust (median/MAD)
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer6 = res6["OUTPUT"]
if isinstance(layer6, str):
    layer6 = QgsVectorLayer(layer6, "anomaly", "ogr")
check(layer6.isValid(), "Anomaly output valid")
check(layer6.featureCount() == 9, f"9 locations (got {layer6.featureCount()})")
anom_fields = {f.name() for f in layer6.fields()}
for req in ["n_anomalies", "max_abs_z", "last_anomaly"]:
    check(req in anom_fields, f"Anomaly field '{req}' present")

# loc_2_2 (baseline_anom) should have at least 1 anomaly
loc_2_2_a = next((f for f in layer6.getFeatures() if f["location_id"] == "loc_2_2"), None)
if loc_2_2_a:
    check(loc_2_2_a["n_anomalies"] >= 1, f"anomaly detected at loc_2_2 (got {loc_2_2_a['n_anomalies']})")


# ============================================================================
# 7. Forecast Backtest
# ============================================================================
print("\n=== 7/8: forecast_backtest ===")
res7 = processing.run(
    "planx_datacube:forecast_backtest",
    {
        "INPUT": panel,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "HOLDOUT": 3,
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer7 = res7["OUTPUT"]
if isinstance(layer7, str):
    layer7 = QgsVectorLayer(layer7, "backtest", "ogr")
check(layer7.isValid(), "Backtest output valid")
check(layer7.featureCount() == 9, f"9 locations (got {layer7.featureCount()})")
bt_fields = {f.name() for f in layer7.fields()}
for req in ["best_method", "best_rmse", "best_mae"]:
    check(req in bt_fields, f"Backtest field '{req}' present")

# best_method should be a non-empty string for locations with enough data
methods_seen = set()
for f in layer7.getFeatures():
    m = f["best_method"]
    if m:
        methods_seen.add(m)
check(len(methods_seen) > 0, f"at least one method evaluated (got {methods_seen})")


# ============================================================================
# 8. Time-Series Forecast
# ============================================================================
print("\n=== 8/8: time_series_forecast ===")
res8 = processing.run(
    "planx_datacube:time_series_forecast",
    {
        "INPUT": panel,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "STEPS_AHEAD": 3,
        "METHOD": 0,        # auto
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer8 = res8["OUTPUT"]
if isinstance(layer8, str):
    layer8 = QgsVectorLayer(layer8, "forecast", "ogr")
check(layer8.isValid(), "Forecast output valid")
check(layer8.featureCount() == 9, f"9 locations (got {layer8.featureCount()})")
fc_fields = {f.name() for f in layer8.fields()}
for req in ["forecast_t1", "forecast_t2", "forecast_t3", "forecast_method"]:
    check(req in fc_fields, f"Forecast field '{req}' present")

# Verify forecast_method is populated
fc_methods = set()
for f in layer8.getFeatures():
    m = f["forecast_method"]
    if m:
        fc_methods.add(m)
check(len(fc_methods) > 0, f"forecast methods used: {fc_methods}")

# Phase 2: verify ARIMA fallback is visible in output when statsmodels is missing.
print("\n=== 8b/8: time_series_forecast (ARIMA explicit, expect fallback) ===")
res8b = processing.run(
    "planx_datacube:time_series_forecast",
    {
        "INPUT": panel,
        "ID_FIELD": "loc_id",
        "TIME_FIELD": "time_step",
        "VALUE_FIELD": "value",
        "STEPS_AHEAD": 3,
        "METHOD": 1,        # ARIMA explicitly
        "OUTPUT": "TEMPORARY_OUTPUT",
    },
)
layer8b = res8b["OUTPUT"]
if isinstance(layer8b, str):
    layer8b = QgsVectorLayer(layer8b, "forecast_arima", "ogr")
check(layer8b.isValid(), "ARIMA forecast output valid")
# Check: since statsmodels is missing in OSGeo4W, ARIMA should fall back.
arima_methods = set()
arima_fell_back = False
for f in layer8b.getFeatures():
    m = f["forecast_method"]
    if m:
        arima_methods.add(m)
        if m != "ARIMA":
            arima_fell_back = True
check(len(arima_methods) > 0, f"ARIMA forecast methods used: {arima_methods}")
check(arima_fell_back, f"ARIMA fell back (statsmodels missing): got {arima_methods}")


# ============================================================================
# SUMMARY
# ============================================================================
print(f"\n{'='*60}")
if fails:
    print(f"E2E QGIS: FAIL ({len(fails)} failures)")
    for f in fails:
        print(f"  FAIL: {f}")
    sys.exit(1)
print(f"E2E QGIS: PASS (all 8 algorithms, {len(provider.algorithms())} registered, 0 failures)")
sys.exit(0)
