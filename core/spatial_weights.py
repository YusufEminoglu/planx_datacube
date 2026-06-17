# -*- coding: utf-8 -*-
"""
Spatial weights — neighbourhood conceptualisation for local spatial statistics.

Pure-Python (math only, no numpy) so the module imports cleanly in headless
unit tests.  Produces a sparse adjacency list ``adj`` where ``adj[i]`` is a list
of ``(j, w)`` neighbour tuples for spatial unit ``i``.

Supported conceptualisations:
  - ``knn``           : k nearest neighbours (binary or inverse-distance weight)
  - ``distance_band`` : every unit within a fixed distance (binary)
  - ``inverse``       : every unit within a cutoff, weighted by 1 / distance

These feed the Getis-Ord Gi* (Emerging Hot Spot Analysis) and Anselin Local
Moran's I (Local Outlier Analysis) engines.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Coord = Tuple[float, float]
Adjacency = List[List[Tuple[int, float]]]


def _dist2(a: Coord, b: Coord) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def auto_distance_band(coords: Sequence[Coord]) -> float:
    """
    Default distance band: the smallest distance that guarantees every unit
    has at least one neighbour (i.e. the maximum over all units of their
    nearest-neighbour distance).  Mirrors the ArcGIS EHSA default.
    """
    n = len(coords)
    if n < 2:
        return 0.0
    max_nn = 0.0
    for i in range(n):
        nn = math.inf
        for j in range(n):
            if i == j:
                continue
            d2 = _dist2(coords[i], coords[j])
            if d2 < nn:
                nn = d2
        if nn is not math.inf:
            max_nn = max(max_nn, nn)
    return math.sqrt(max_nn)


def build_weights(
    coords: Sequence[Coord],
    mode: str = "knn",
    k: int = 8,
    distance: float = 0.0,
    include_self: bool = False,
    row_standardize: bool = False,
    inverse_power: float = 1.0,
) -> Adjacency:
    """
    Build a spatial-weights adjacency list.

    Parameters
    ----------
    coords : sequence of (x, y)
        Representative coordinate (e.g. centroid) of each spatial unit.
    mode : {"knn", "distance_band", "inverse"}
    k : int
        Neighbour count for ``knn`` (clamped to ``n - 1``).
    distance : float
        Distance band / cutoff for ``distance_band`` and ``inverse``.
        ``0`` triggers :func:`auto_distance_band`.
    include_self : bool
        Add a self term ``(i, 1.0)`` — required for Getis-Ord Gi*.
    row_standardize : bool
        Divide each row's weights so they sum to 1 — standard for Local
        Moran's I spatial lag.
    inverse_power : float
        Exponent for ``inverse`` weights (1 = 1/d, 2 = 1/d²).

    Returns
    -------
    Adjacency — ``adj[i]`` = list of ``(j, weight)``.
    """
    n = len(coords)
    adj: Adjacency = [[] for _ in range(n)]
    if n < 2:
        if include_self:
            for i in range(n):
                adj[i].append((i, 1.0))
        return adj

    if mode == "knn":
        kk = max(1, min(k, n - 1))
        for i in range(n):
            dists = sorted(
                ((_dist2(coords[i], coords[j]), j) for j in range(n) if j != i),
                key=lambda t: t[0],
            )
            for d2, j in dists[:kk]:
                adj[i].append((j, 1.0))
    elif mode == "inverse":
        d = distance if distance > 0 else auto_distance_band(coords)
        d2cut = d * d
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                d2 = _dist2(coords[i], coords[j])
                if d2 <= d2cut:
                    dd = math.sqrt(d2)
                    w = 1.0 / (dd ** inverse_power) if dd > 0 else 0.0
                    if w > 0:
                        adj[i].append((j, w))
    else:  # distance_band
        d = distance if distance > 0 else auto_distance_band(coords)
        d2cut = d * d
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if _dist2(coords[i], coords[j]) <= d2cut:
                    adj[i].append((j, 1.0))

    if row_standardize:
        for i in range(n):
            s = sum(w for _, w in adj[i])
            if s > 0:
                adj[i] = [(j, w / s) for j, w in adj[i]]

    if include_self:
        for i in range(n):
            adj[i].append((i, 1.0))

    return adj


def neighbour_counts(adj: Adjacency) -> List[int]:
    """Number of neighbours per unit (handy for diagnostics / warnings)."""
    return [len(row) for row in adj]
