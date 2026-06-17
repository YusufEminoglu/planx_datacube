# -*- coding: utf-8 -*-
"""
Time-series statistics — robust anomaly detection and trend classification.

Pure-Python helpers shared by the Temporal Anomaly Detection and Temporal
Trend Analysis Processing algorithms.  No numpy dependency at import time.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

# ── Trend classification codes ──────────────────────────────────────────
TREND_NONE = 0
TREND_INCREASING = 1
TREND_DECREASING = 2

TREND_LABELS = {
    TREND_NONE: "No significant trend",
    TREND_INCREASING: "Increasing",
    TREND_DECREASING: "Decreasing",
}


def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return 0.5 * (s[mid - 1] + s[mid])


def mean_std(values: Sequence[float]) -> Tuple[float, float]:
    """Population mean and standard deviation."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(var)


def robust_zscores(series: Sequence[float]) -> List[float]:
    """
    Modified z-score using the median absolute deviation (MAD).

        z_i = 0.6745 * (x_i - median) / MAD

    Falls back to the classic (x - mean) / std when MAD is zero (e.g. more
    than half the points share a single value).  Returns zeros for series
    shorter than three points.
    """
    n = len(series)
    if n < 3:
        return [0.0] * n
    med = _median(series)
    abs_dev = [abs(v - med) for v in series]
    mad = _median(abs_dev)
    if mad > 1e-12:
        return [0.6745 * (v - med) / mad for v in series]
    mean, std = mean_std(series)
    if std <= 1e-12:
        return [0.0] * n
    return [(v - mean) / std for v in series]


def standard_zscores(series: Sequence[float]) -> List[float]:
    """Classic (x - mean) / std z-scores."""
    n = len(series)
    if n < 2:
        return [0.0] * n
    mean, std = mean_std(series)
    if std <= 1e-12:
        return [0.0] * n
    return [(v - mean) / std for v in series]


def detect_anomalies(
    series: Sequence[float],
    threshold: float = 3.0,
    robust: bool = True,
) -> dict:
    """
    Flag time points whose (robust) z-score exceeds ``threshold`` in
    absolute value.

    Returns a summary dict::

        {
          "zscores": [...],          # per-point z-score
          "flags":   [bool, ...],    # |z| >= threshold
          "n_anomalies": int,
          "anomaly_rate": float,     # fraction of points flagged
          "max_abs_z": float,
          "first_index": int | -1,   # index of earliest anomaly
          "last_index": int | -1,    # index of latest anomaly
          "last_is_anomaly": bool,   # is the most recent point anomalous?
          "last_z": float,
        }
    """
    z = robust_zscores(series) if robust else standard_zscores(series)
    flags = [abs(v) >= threshold for v in z]
    idxs = [i for i, f in enumerate(flags) if f]
    n = len(series)
    return {
        "zscores": z,
        "flags": flags,
        "n_anomalies": len(idxs),
        "anomaly_rate": (len(idxs) / n) if n else 0.0,
        "max_abs_z": max((abs(v) for v in z), default=0.0),
        "first_index": idxs[0] if idxs else -1,
        "last_index": idxs[-1] if idxs else -1,
        "last_is_anomaly": bool(flags[-1]) if flags else False,
        "last_z": z[-1] if z else 0.0,
    }


def classify_trend(p_value: float, sen_slope: float, p_threshold: float = 0.05) -> int:
    """Map a Mann-Kendall result to a trend code."""
    if p_value < p_threshold and sen_slope > 0:
        return TREND_INCREASING
    if p_value < p_threshold and sen_slope < 0:
        return TREND_DECREASING
    return TREND_NONE


def sen_intercept(series: Sequence[float], slope: float) -> float:
    """
    Theil-Sen intercept: median of ``x_t - slope * t`` over the series,
    using integer time positions 0..n-1.
    """
    if not series:
        return 0.0
    return _median([v - slope * t for t, v in enumerate(series)])
