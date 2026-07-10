# -*- coding: utf-8 -*-
"""
Emerging Hot Spot Analysis (EHSA) Engine.

Implements the full Getis-Ord Gi* + Mann-Kendall trend test pipeline
to classify each spatial unit into one of 17 spatiotemporal patterns.

Patterns (ESRI-compatible):
  0  = Not Significant
  1  = New Hot Spot
  2  = Consecutive Hot Spot
  3  = Intensifying Hot Spot
  4  = Persistent Hot Spot
  5  = Diminishing Hot Spot
  6  = Sporadic Hot Spot
  7  = Oscillating Hot Spot
  8  = Historical Hot Spot
  9  = New Cold Spot
  10 = Consecutive Cold Spot
  11 = Intensifying Cold Spot
  12 = Persistent Cold Spot
  13 = Diminishing Cold Spot
  14 = Sporadic Cold Spot
  15 = Oscillating Cold Spot
  16 = Historical Cold Spot
"""
from __future__ import annotations

import math
from typing import List, Tuple, Optional


# ---------------------------------------------------------------------------
# Getis-Ord Gi* local statistic
# ---------------------------------------------------------------------------

def getis_ord_g_star(
    values: List[float],
    weights: Optional[List[float]] = None,
) -> List[float]:
    """
    Compute Getis-Ord Gi* z-scores for a set of values.

    Without a spatial weights matrix, this computes the standardised
    Gi* treating each value's contribution equally — a 'self-only'
    variant useful when spatial neighbours are not defined.

    Parameters
    ----------
    values : list[float]
        Array of values for the spatial units at a given time step.
    weights : list[float] | None
        Spatial weights (row-standardised). If None, equal weights.

    Returns
    -------
    list[float] — Gi* z-scores (same length as input).
    """
    n = len(values)
    if n < 3:
        return [0.0] * n

    mean_val = sum(values) / n
    variance = sum((v - mean_val) ** 2 for v in values) / n
    std_dev = math.sqrt(variance) if variance > 0 else 1e-12

    if weights is None:
        # self-only: Gi* ≈ (x_i - mean) / std
        return [(v - mean_val) / std_dev for v in values]

    # with spatial weights: Gi* = (Σ w_ij * x_j - mean * Σ w_ij) / (std * sqrt_term)
    z_scores = []
    w_sum = sum(weights)
    s1 = sum(w ** 2 for w in weights)

    for i in range(n):
        weighted_sum = sum(weights[j] * values[j] for j in range(n))
        z = (weighted_sum - mean_val * w_sum) / (std_dev * math.sqrt(n * s1 - w_sum ** 2) / (n - 1) + 1e-12)
        z_scores.append(z)

    return z_scores


def getis_ord_gi_star_matrix(
    values: List[float],
    adjacency: List[List[Tuple[int, float]]],
) -> List[float]:
    """
    Proper Getis-Ord Gi* using a spatial-weights adjacency list.

    Implements the Ord & Getis (1995) standardised local statistic::

        Gi* = (Σ_j w_ij x_j − X̄ Σ_j w_ij)
              / ( S · sqrt[ (n Σ_j w_ij² − (Σ_j w_ij)²) / (n − 1) ] )

    with X̄ the global mean and S the global (population) standard deviation.
    The adjacency **must include the self term** ``(i, w_ii)`` — Gi* (starred)
    counts unit *i* among its own neighbours.

    Parameters
    ----------
    values : list[float]
        Attribute value for each spatial unit at one time step.
    adjacency : list[list[(int, float)]]
        ``adjacency[i]`` = neighbour ``(j, weight)`` tuples for unit ``i``.

    Returns
    -------
    list[float] — Gi* z-scores (high positive = hot, high negative = cold).
    """
    n = len(values)
    if n < 3:
        return [0.0] * n

    mean_val = sum(values) / n
    second = sum(v * v for v in values) / n
    s = math.sqrt(max(second - mean_val * mean_val, 0.0))
    if s <= 1e-12:
        return [0.0] * n

    z_scores = []
    for i in range(n):
        row = adjacency[i] if i < len(adjacency) else []
        if not row:
            z_scores.append(0.0)
            continue
        w_sum = sum(w for _, w in row)
        w_sq = sum(w * w for _, w in row)
        weighted = sum(w * values[j] for j, w in row)
        denom = s * math.sqrt(max((n * w_sq - w_sum * w_sum) / (n - 1), 1e-18))
        z_scores.append((weighted - mean_val * w_sum) / denom if denom > 1e-18 else 0.0)

    return z_scores


# ---------------------------------------------------------------------------
# Mann-Kendall Trend Test
# ---------------------------------------------------------------------------

def mann_kendall_test(series: List[float]) -> Tuple[float, float, float]:
    """
    Compute the Mann-Kendall trend statistic.

    Parameters
    ----------
    series : list[float]
        Time series values.

    Returns
    -------
    (tau, p_value, sen_slope) : (float, float, float)
        tau       — Kendall's τ correlation (-1 to 1)
        p_value   — two-tailed p-value
        sen_slope — Theil-Sen slope estimator (robust trend)
    """
    n = len(series)
    if n < 3:
        return 0.0, 1.0, 0.0

    # Kendall's S
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            if series[j] > series[i]:
                s += 1
            elif series[j] < series[i]:
                s -= 1

    # variance of S
    # handle ties
    tie_groups = {}
    for v in series:
        tie_groups[v] = tie_groups.get(v, 0) + 1

    tie_correction = 0
    for cnt in tie_groups.values():
        if cnt > 1:
            tie_correction += cnt * (cnt - 1) * (2 * cnt + 5)

    var_s = (n * (n - 1) * (2 * n + 5) - tie_correction) / 18.0

    if var_s > 0:
        z = (s - 1) / math.sqrt(var_s) if s > 0 else (s + 1) / math.sqrt(var_s) if s < 0 else 0.0
    else:
        z = 0.0

    # p-value from normal approximation
    p_value = 2.0 * (1.0 - _normal_cdf(abs(z)))

    # Theil-Sen slope
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            if series[j] != series[i]:
                slopes.append((series[j] - series[i]) / (j - i))
    slopes.sort()
    if slopes:
        sen_slope = slopes[len(slopes) // 2]
    else:
        sen_slope = 0.0

    tau = s / (n * (n - 1) / 2.0) if n > 1 else 0.0
    return tau, p_value, sen_slope


def _normal_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun 26.2.17)."""
    if x < -10:
        return 0.0
    if x > 10:
        return 1.0
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# EHSA classification
# ---------------------------------------------------------------------------

# Pattern enum
EHSA_NOT_SIG = 0
EHSA_NEW_HOT = 1
EHSA_CONSECUTIVE_HOT = 2
EHSA_INTENSIFYING_HOT = 3
EHSA_PERSISTENT_HOT = 4
EHSA_DIMINISHING_HOT = 5
EHSA_SPORADIC_HOT = 6
EHSA_OSCILLATING_HOT = 7
EHSA_HISTORICAL_HOT = 8
EHSA_NEW_COLD = 9
EHSA_CONSECUTIVE_COLD = 10
EHSA_INTENSIFYING_COLD = 11
EHSA_PERSISTENT_COLD = 12
EHSA_DIMINISHING_COLD = 13
EHSA_SPORADIC_COLD = 14
EHSA_OSCILLATING_COLD = 15
EHSA_HISTORICAL_COLD = 16

EHSA_LABELS = {
    0: "Not Significant",
    1: "New Hot Spot",
    2: "Consecutive Hot Spot",
    3: "Intensifying Hot Spot",
    4: "Persistent Hot Spot",
    5: "Diminishing Hot Spot",
    6: "Sporadic Hot Spot",
    7: "Oscillating Hot Spot",
    8: "Historical Hot Spot",
    9: "New Cold Spot",
    10: "Consecutive Cold Spot",
    11: "Intensifying Cold Spot",
    12: "Persistent Cold Spot",
    13: "Diminishing Cold Spot",
    14: "Sporadic Cold Spot",
    15: "Oscillating Cold Spot",
    16: "Historical Cold Spot",
}


def classify_ehsa_pattern(
    z_scores_by_time: List[List[float]],
    p_threshold: float = 0.05,
) -> List[int]:
    """
    Classify each spatial unit into one of 17 EHSA patterns.

    Parameters
    ----------
    z_scores_by_time : list[list[float]]
        List of per-timestep Gi* z-scores, shape (n_times, n_units).
    p_threshold : float
        Significance threshold for Gi* (two-tailed).

    Returns
    -------
    list[int] — EHSA pattern code for each spatial unit (n_units).
    """
    n_times = len(z_scores_by_time)
    if n_times < 3:
        return [EHSA_NOT_SIG] * len(z_scores_by_time[0])

    n_units = len(z_scores_by_time[0])
    z_critical = _normal_quantile(1.0 - p_threshold / 2.0)

    patterns = []
    for unit in range(n_units):
        z_series = [z_scores_by_time[t][unit] for t in range(n_times)]
        bin_series = [1 if abs(z) >= z_critical and z > 0
                      else -1 if abs(z) >= z_critical and z < 0
                      else 0
                      for z in z_series]

        # Mann-Kendall test
        tau, p_mk, sen_slope = mann_kendall_test(z_series)
        trend_up = (sen_slope > 0 and p_mk < p_threshold)
        trend_down = (sen_slope < 0 and p_mk < p_threshold)

        hot_count = sum(1 for b in bin_series if b == 1)
        cold_count = sum(1 for b in bin_series if b == -1)
        sig_count = hot_count + cold_count

        # Determine if mostly hot or cold
        if sig_count < n_times * 0.2:
            patterns.append(EHSA_NOT_SIG)
            continue

        is_hot = hot_count >= cold_count
        recent_half = bin_series[len(bin_series) // 2:]
        old_half = bin_series[:len(bin_series) // 2]
        recent_sig = sum(1 for b in recent_half if b != 0)
        old_sig = sum(1 for b in old_half if b != 0)

        if is_hot:
            patterns.append(_classify_hot(bin_series, trend_up, trend_down, recent_sig, old_sig, sig_count, n_times))
        else:
            patterns.append(_classify_cold(bin_series, trend_up, trend_down, recent_sig, old_sig, sig_count, n_times))

    return patterns


def _classify_hot(bin_series, trend_up, trend_down, recent_sig, old_sig, sig_count, n_times):
    """Classify a primarily-hot series."""
    consecutive = _max_consecutive(bin_series, 1)

    if old_sig == 0 and recent_sig > 0:
        return EHSA_NEW_HOT
    if consecutive >= n_times * 0.9:
        if trend_up:
            return EHSA_INTENSIFYING_HOT
        if trend_down:
            return EHSA_DIMINISHING_HOT
        return EHSA_PERSISTENT_HOT
    if consecutive >= n_times * 0.5:
        return EHSA_CONSECUTIVE_HOT
    if old_sig > 0 and recent_sig == 0:
        return EHSA_HISTORICAL_HOT
    if _has_oscillation(bin_series):
        return EHSA_OSCILLATING_HOT
    if sig_count < n_times * 0.5:
        return EHSA_SPORADIC_HOT
    return EHSA_PERSISTENT_HOT


def _classify_cold(bin_series, trend_up, trend_down, recent_sig, old_sig, sig_count, n_times):
    """Classify a primarily-cold series."""
    consecutive = _max_consecutive(bin_series, -1)

    if old_sig == 0 and recent_sig > 0:
        return EHSA_NEW_COLD
    if consecutive >= n_times * 0.9:
        if trend_up:
            return EHSA_DIMINISHING_COLD
        if trend_down:
            return EHSA_INTENSIFYING_COLD
        return EHSA_PERSISTENT_COLD
    if consecutive >= n_times * 0.5:
        return EHSA_CONSECUTIVE_COLD
    if old_sig > 0 and recent_sig == 0:
        return EHSA_HISTORICAL_COLD
    if _has_oscillation(bin_series):
        return EHSA_OSCILLATING_COLD
    if sig_count < n_times * 0.5:
        return EHSA_SPORADIC_COLD
    return EHSA_PERSISTENT_COLD


def _max_consecutive(bin_series: list, target: int) -> int:
    max_run = 0
    current = 0
    for v in bin_series:
        if v == target:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _has_oscillation(bin_series: list) -> bool:
    """Check for alternating positive/negative significant bins."""
    switches = 0
    prev = 0
    for v in bin_series:
        if v != 0 and v != prev:
            switches += 1
        if v != 0:
            prev = v
    return switches >= 3


def _normal_quantile(p: float) -> float:
    """Approximate normal quantile (inverse CDF)."""
    if p <= 0.0:
        return -10.0
    if p >= 1.0:
        return 10.0
    # rational approximation (A&S 26.2.23)
    if p > 0.5:
        return -_normal_quantile(1.0 - p)
    t = math.sqrt(-2.0 * math.log(max(p, 1e-12)))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return -(t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t))
