# -*- coding: utf-8 -*-
"""
Anselin Local Moran's I — local indicator of spatial association (LISA).

Classifies every spatial unit into a cluster / outlier type:

  0  Not Significant
  1  High-High   (hot cluster)
  2  Low-Low     (cold cluster)
  3  Low-High    (low value among high neighbours — spatial outlier)
  4  High-Low    (high value among low neighbours — spatial outlier)

Significance comes from a **conditional permutation** test (Anselin 1995):
for each unit the value is held fixed while its neighbours are re-sampled at
random from the remaining units, building a reference distribution of I.
A fixed integer-seeded ``random.Random`` keeps results deterministic across
processes (no hash-seed surprises).

Pure-Python (no numpy) so it imports in headless unit tests.
"""
from __future__ import annotations

import random
from typing import List, Sequence, Tuple

LISA_NS = 0
LISA_HH = 1
LISA_LL = 2
LISA_LH = 3
LISA_HL = 4

LISA_LABELS = {
    LISA_NS: "Not Significant",
    LISA_HH: "High-High Cluster",
    LISA_LL: "Low-Low Cluster",
    LISA_LH: "Low-High Outlier",
    LISA_HL: "High-Low Outlier",
}


def local_morans_i(
    values: Sequence[float],
    adjacency: List[List[Tuple[int, float]]],
    permutations: int = 999,
    p_threshold: float = 0.05,
    seed: int = 1234567,
) -> dict:
    """
    Compute Local Moran's I with a conditional-permutation pseudo p-value.

    Parameters
    ----------
    values : sequence of float
    adjacency : list[list[(int, float)]]
        Neighbour weights **without** a self term; row-standardised weights
        are recommended so the spatial lag is a neighbour mean.
    permutations : int
        Number of conditional permutations (>= 0; 0 disables the test, then
        only deviational sign decides the cluster type).
    p_threshold : float
        Pseudo p-value cut-off for significance.
    seed : int
        Deterministic RNG seed.

    Returns
    -------
    dict with keys ``I`` (local I), ``z`` (standardised deviation),
    ``lag`` (spatial lag of the deviation), ``p`` (pseudo p-value),
    ``cluster`` (LISA code per unit).
    """
    n = len(values)
    if n < 3:
        zeros = [0.0] * n
        return {"I": zeros[:], "z": zeros[:], "lag": zeros[:],
                "p": [1.0] * n, "cluster": [LISA_NS] * n}

    mean = sum(values) / n
    dev = [v - mean for v in values]
    m2 = sum(d * d for d in dev) / n
    if m2 <= 1e-18:
        return {"I": [0.0] * n, "z": [0.0] * n, "lag": [0.0] * n,
                "p": [1.0] * n, "cluster": [LISA_NS] * n}

    std = m2 ** 0.5
    z_std = [d / std for d in dev]

    i_vals: List[float] = []
    lags: List[float] = []
    p_vals: List[float] = []
    clusters: List[int] = []
    rng = random.Random(seed)  # nosec B311 — deterministic permutation testing, not security-sensitive

    for i in range(n):
        row = adjacency[i] if i < len(adjacency) else []
        lag = sum(w * dev[j] for j, w in row)
        ii = (dev[i] / m2) * lag
        lags.append(lag)
        i_vals.append(ii)

        # conditional permutation
        if permutations and row:
            k = len(row)
            weights = [w for _, w in row]
            others = [dev[j] for j in range(n) if j != i]
            ge = 0
            abs_obs = abs(ii)
            for _ in range(permutations):
                sample = rng.sample(others, k) if k <= len(others) else others
                perm_lag = sum(weights[t] * sample[t] for t in range(len(sample)))
                perm_i = (dev[i] / m2) * perm_lag
                if abs(perm_i) >= abs_obs:
                    ge += 1
            p = (ge + 1) / (permutations + 1)
        else:
            p = 1.0
        p_vals.append(p)

        # cluster classification (lag expressed in std units for sign clarity)
        lag_std = lag / std
        if (permutations == 0 or p < p_threshold) and abs(z_std[i]) > 1e-9:
            if z_std[i] > 0 and lag_std >= 0:
                clusters.append(LISA_HH)
            elif z_std[i] < 0 and lag_std <= 0:
                clusters.append(LISA_LL)
            elif z_std[i] < 0 and lag_std > 0:
                clusters.append(LISA_LH)
            else:
                clusters.append(LISA_HL)
        else:
            clusters.append(LISA_NS)

    return {"I": i_vals, "z": z_std, "lag": lags, "p": p_vals, "cluster": clusters}
