# -*- coding: utf-8 -*-
"""
Panel data reader — shared (location, time, value) ingestion.

Every spatiotemporal analysis algorithm in DataCube Lab (EHSA, Forecast,
Trend, Anomaly, Backtest, Local Moran's I) consumes the same long-format
panel: one feature per *location × time step*.  This module centralises the
parsing, validation and per-location geometry collection so the algorithms
stay thin and behave identically.

No top-level QGIS import: features are duck-typed, so the module imports in
headless unit tests.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional


class PanelData:
    """Parsed long-format panel ready for analysis."""

    def __init__(self) -> None:
        self.loc_times: Dict[str, Dict[int, float]] = {}
        self.loc_geom: Dict[str, object] = {}
        self.locations: List[str] = []
        self.times: List[int] = []

    # -- accessors -------------------------------------------------------
    def series(self, loc: str, fill: Optional[float] = 0.0) -> List[float]:
        """Time-aligned values for one location over :pyattr:`times`."""
        tm = self.loc_times.get(loc, {})
        if fill is None:
            return [tm[t] for t in self.times if t in tm]
        return [tm.get(t, fill) for t in self.times]

    def raw_series(self, loc: str) -> List[float]:
        """Values for a location ordered by its own observed time steps."""
        tm = self.loc_times.get(loc, {})
        return [tm[t] for t in sorted(tm.keys())]

    @property
    def n_locations(self) -> int:
        return len(self.locations)

    @property
    def n_times(self) -> int:
        return len(self.times)


def read_panel(source, id_field: str, time_field: str, value_field: str) -> PanelData:
    """
    Read a long-format panel from a QgsFeatureSource (or any iterable of
    features exposing ``__getitem__`` and ``geometry()``).

    Rows with null / non-finite / non-numeric time or value are skipped.
    Time is coerced to int (``int(float(raw))``) so heterogeneous numeric
    encodings (2020, 2020.0) collapse to the same step.  The first valid,
    non-empty geometry seen per location is retained.
    """
    panel = PanelData()
    times: set = set()
    locs: set = set()

    for feat in source.getFeatures():
        loc_id = feat[id_field]
        if loc_id is None:
            continue
        loc_id = str(loc_id)
        raw_t = feat[time_field]
        raw_v = feat[value_field]
        if raw_t is None or raw_v is None:
            continue
        try:
            t = int(float(raw_t))
            v = float(raw_v)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(v):
            continue
        locs.add(loc_id)
        times.add(t)
        panel.loc_times.setdefault(loc_id, {})[t] = v
        if loc_id not in panel.loc_geom:
            try:
                g = feat.geometry()
            except Exception:
                g = None
            if g is not None and not g.isEmpty():
                panel.loc_geom[loc_id] = g

    panel.locations = sorted(locs)
    panel.times = sorted(times)
    return panel


def centroid_xy(geom):
    """
    Return the (x, y) centroid of a geometry, or ``None`` when unavailable.
    Works for point, line and polygon geometries.
    """
    if geom is None:
        return None
    try:
        if geom.isEmpty():
            return None
        c = geom.centroid()
        if c is None or c.isEmpty():
            return None
        p = c.asPoint()
        return (p.x(), p.y())
    except Exception:
        return None
