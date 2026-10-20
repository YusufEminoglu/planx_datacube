# -*- coding: utf-8 -*-
"""
Cube grid model — a lightweight, QGIS-free view of a space-time panel.

The Processing algorithms produce long-format panels (one row per cell and
time step).  The dashboard needs a rectangular view for heatmaps, voxel
previews and sparklines.  This module turns a :class:`core.panel.PanelData`
into that rectangular grid and provides the small amount of statistics the
UI displays.

It deliberately has no QGIS or numpy import so it can be unit-tested in a
plain Python interpreter.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

NAN = float("nan")


def _natural_key(value: str):
    """Sort ``cell_2`` before ``cell_10`` instead of after it."""
    parts = re.split(r"(\d+)", str(value))
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def _mean(values: Sequence[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    return sum(finite) / len(finite) if finite else NAN


class CubeGrid:
    """Rectangular view of a space-time cube.

    Attributes
    ----------
    cell_ids:
        One label per row (usually the panel's ``cell_id``).
    times:
        Numeric time coordinate per column.
    time_labels:
        Display labels for the time columns.
    values:
        ``values[cell][time]``; missing observations are ``NaN``.
    counts:
        Optional event counts with the same shape as ``values``.
    """

    def __init__(
        self,
        cell_ids: Sequence[str],
        times: Sequence[float],
        values: Sequence[Sequence[float]],
        counts: Optional[Sequence[Sequence[float]]] = None,
        time_labels: Optional[Sequence[str]] = None,
        source: str = "",
    ):
        self.cell_ids = [str(c) for c in cell_ids]
        self.times = [float(t) for t in times]
        self.time_labels = (
            [str(t) for t in time_labels]
            if time_labels is not None
            else [self._format_time(t) for t in self.times]
        )
        self.values = [[float(v) for v in row] for row in values]
        self.counts = (
            [[float(v) for v in row] for row in counts]
            if counts is not None else None
        )
        self.source = source
        # Filled by :meth:`downsample`; maps display rows/columns back to the
        # original grid so a click in a downsampled heatmap still resolves to
        # a real cell and time index.
        self.cell_blocks: Optional[List[Tuple[int, int]]] = None
        self.time_blocks: Optional[List[Tuple[int, int]]] = None

    # -- constructors ----------------------------------------------------
    @classmethod
    def from_panel(cls, panel, source: str = "") -> "CubeGrid":
        """Build a rectangular grid from a :class:`core.panel.PanelData`."""
        times = list(panel.times)
        cells = sorted(panel.locations, key=_natural_key)
        values: List[List[float]] = []
        counts: List[List[float]] = []
        for cell in cells:
            series = panel.loc_times.get(cell, {})
            values.append([series.get(t, NAN) for t in times])
            counts.append([1.0 if t in series else 0.0 for t in times])
        return cls(cells, times, values, counts, source=source)

    @classmethod
    def from_netcdf(cls, path: str, variable: str = "") -> "CubeGrid":
        """Read a 3-D (time, y, x) netCDF cube into the UI model."""
        import netCDF4  # optional dependency, imported lazily

        with netCDF4.Dataset(path, "r") as ds:
            names = [n for n in ds.variables
                     if n not in ("x", "y", "time", "crs",
                                  "x_bnds", "y_bnds", "time_label")]
            if not names:
                raise ValueError("No data variables found in the netCDF file.")
            var_name = variable if variable in names else names[0]
            var = ds.variables[var_name]
            if var.ndim != 3:
                raise ValueError(
                    f"Variable '{var_name}' is {var.ndim}-D; expected (time, y, x).")
            raw = var[:]
            times = list(ds.variables["time"][:]) if "time" in ds.variables \
                else list(range(raw.shape[0]))
            labels = None
            if "time_label" in ds.variables:
                labels = []
                for row in ds.variables["time_label"][:]:
                    try:
                        label = b"".join(row).decode("utf-8")
                        labels.append(label.replace("\x00", "").strip())
                    except Exception:
                        labels.append("")
            cells = []
            for y in range(raw.shape[1]):
                for x in range(raw.shape[2]):
                    cells.append(f"y{y}_x{x}")
            values = []
            for y in range(raw.shape[1]):
                for x in range(raw.shape[2]):
                    series = []
                    for t in range(raw.shape[0]):
                        v = raw[t, y, x]
                        if getattr(v, "mask", False) is not False:
                            v = NAN
                        series.append(float(v))
                    values.append(series)
            counts = [[1.0 if math.isfinite(v) else 0.0 for v in row]
                      for row in values]
        return cls(cells, times, values, counts, time_labels=labels,
                   source=path)

    # -- basic accessors -------------------------------------------------
    @property
    def n_cells(self) -> int:
        return len(self.cell_ids)

    @property
    def n_times(self) -> int:
        return len(self.times)

    def series(self, cell_index: int) -> List[float]:
        return list(self.values[cell_index])

    def time_slice(self, time_index: int) -> List[float]:
        return [row[time_index] for row in self.values]

    def finite_values(self) -> List[float]:
        return [v for row in self.values for v in row if math.isfinite(v)]

    # -- statistics ------------------------------------------------------
    def stats(self) -> Dict[str, float]:
        finite = self.finite_values()
        total = self.n_cells * self.n_times
        count_total = 0.0
        if self.counts is not None:
            count_total = sum(v for row in self.counts for v in row
                              if math.isfinite(v))
        return {
            "n_cells": float(self.n_cells),
            "n_times": float(self.n_times),
            "n_values": float(len(finite)),
            "coverage": (len(finite) / total) if total else 0.0,
            "min": min(finite) if finite else NAN,
            "max": max(finite) if finite else NAN,
            "mean": (sum(finite) / len(finite)) if finite else NAN,
            "total": sum(finite) if finite else 0.0,
            "count_total": count_total,
        }

    def value_range(self) -> Tuple[float, float]:
        finite = self.finite_values()
        if not finite:
            return (0.0, 1.0)
        low, high = min(finite), max(finite)
        if abs(high - low) < 1e-12:
            high = low + 1.0
        return (low, high)

    # -- rendering helpers ----------------------------------------------
    def downsample(self, max_cells: int = 48,
                   max_times: int = 48) -> "CubeGrid":
        """Aggregate the grid to at most ``max_cells`` × ``max_times``.

        Aggregation uses the mean of finite values per block.  This keeps
        the painter responsive for large cubes without changing the
        underlying data.
        """
        cell_blocks = _blocks(self.n_cells, max_cells)
        time_blocks = _blocks(self.n_times, max_times)
        values: List[List[float]] = []
        counts: List[List[float]] = []
        for c0, c1 in cell_blocks:
            row: List[float] = []
            count_row: List[float] = []
            for t0, t1 in time_blocks:
                block = [self.values[c][t]
                         for c in range(c0, c1)
                         for t in range(t0, t1)]
                row.append(_mean(block))
                if self.counts is not None:
                    count_row.append(sum(
                        self.counts[c][t]
                        for c in range(c0, c1)
                        for t in range(t0, t1)))
                else:
                    count_row.append(float(sum(
                        1 for v in block if math.isfinite(v))))
            values.append(row)
            counts.append(count_row)
        labels = []
        for t0, t1 in time_blocks:
            if t1 - t0 == 1:
                labels.append(self.time_labels[t0])
            else:
                labels.append(f"{self.time_labels[t0]}–{self.time_labels[t1 - 1]}")
        cell_ids = []
        for c0, c1 in cell_blocks:
            if c1 - c0 == 1:
                cell_ids.append(self.cell_ids[c0])
            else:
                cell_ids.append(f"{self.cell_ids[c0]}–{self.cell_ids[c1 - 1]}")
        times = [self.times[(t0 + t1 - 1) // 2] for t0, t1 in time_blocks]
        result = CubeGrid(cell_ids, times, values, counts,
                          time_labels=labels, source=self.source)
        result.cell_blocks = cell_blocks
        result.time_blocks = time_blocks
        return result

    @staticmethod
    def _format_time(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:g}"


def _blocks(count: int, maximum: int) -> List[Tuple[int, int]]:
    """Return contiguous half-open blocks covering ``count`` items."""
    if count <= 0:
        return []
    maximum = max(1, int(maximum))
    if count <= maximum:
        return [(i, i + 1) for i in range(count)]
    size = int(math.ceil(count / maximum))
    return [(i, min(i + size, count)) for i in range(0, count, size)]
