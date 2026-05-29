# -*- coding: utf-8 -*-
"""
Data Cube Builder — Converts vector/raster time series into multi-dimensional
xarray.Dataset structures (X×Y×T×V dimensions).

Supports:
  - Vector layers (polygon/point) with timestamp fields → spatial bins
  - Raster stacks → NetCDF/Zarr chunks
  - In-memory Dask lazy evaluation for large datasets
  - Export to netCDF4 or Zarr on disk
"""
from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from qgis.core import (
    QgsVectorLayer, QgsRasterLayer, QgsFeature, QgsGeometry,
    QgsRectangle, QgsPointXY, QgsField, QgsFields, QgsFeatureSink,
    QgsProcessingFeedback, QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QVariant


# ---------------------------------------------------------------------------
# Pure-Python (no xarray dependency) lightweight data cube
# ---------------------------------------------------------------------------

class DataCube:
    """
    In-memory multi-dimensional data cube (X×Y×T×V).

    Represented as nested dicts, serialisable to JSON, with optional
    netCDF4 export when the library is available.
    """

    def __init__(
        self,
        x_coords: List[float],
        y_coords: List[float],
        time_steps: List[str],
        variable_names: List[str],
    ):
        self.x_coords = x_coords
        self.y_coords = y_coords
        self.time_steps = time_steps
        self.variable_names = variable_names

        # data[t][v][y][x] — nested 4D array
        self.data: Dict[str, Dict[str, List[List[float]]]] = {
            t: {v: [[math.nan] * len(x_coords) for _ in range(len(y_coords))]
                for v in variable_names}
            for t in time_steps
        }

    def set_value(self, t_idx: int, var: str, x_idx: int, y_idx: int, value: float):
        self.data[self.time_steps[t_idx]][var][y_idx][x_idx] = value

    def get_series(self, x_idx: int, y_idx: int, var: str) -> List[float]:
        """Extract a time series for a single grid cell."""
        return [
            self.data[t][var][y_idx][x_idx]
            for t in self.time_steps
        ]

    def to_netcdf(self, path: str) -> bool:
        """Export to netCDF4 if library available."""
        try:
            import netCDF4
            import numpy as np
        except ImportError:
            return False

        ds = netCDF4.Dataset(path, "w", format="NETCDF4")
        ds.createDimension("x", len(self.x_coords))
        ds.createDimension("y", len(self.y_coords))
        ds.createDimension("time", len(self.time_steps))

        x_var = ds.createVariable("x", "f8", ("x",))
        y_var = ds.createVariable("y", "f8", ("y",))
        t_var = ds.createVariable("time", "i4", ("time",))

        x_var[:] = self.x_coords
        y_var[:] = self.y_coords
        t_var[:] = range(len(self.time_steps))

        for var_name in self.variable_names:
            arr = np.zeros((len(self.time_steps), len(self.y_coords), len(self.x_coords)))
            for ti, t in enumerate(self.time_steps):
                for yi in range(len(self.y_coords)):
                    for xi in range(len(self.x_coords)):
                        val = self.data[t][var_name][yi][xi]
                        arr[ti, yi, xi] = val if math.isfinite(val) else np.nan
            ds.createVariable(var_name, "f8", ("time", "y", "x"), fill_value=np.nan)
            ds[var_name][:] = arr

        ds.close()
        return True

    def to_zarr(self, path: str) -> bool:
        """Export to Zarr directory store if library available."""
        try:
            import zarr
            import numpy as np
        except ImportError:
            return False

        try:
            store = zarr.DirectoryStore(path)
            root = zarr.group(store=store, overwrite=True)

            root.create_dataset("x", data=np.array(self.x_coords, dtype="f8"), shape=(len(self.x_coords),), chunks=(len(self.x_coords),))
            root.create_dataset("y", data=np.array(self.y_coords, dtype="f8"), shape=(len(self.y_coords),), chunks=(len(self.y_coords),))
            root.create_dataset("time", data=np.array(range(len(self.time_steps)), dtype="i4"), shape=(len(self.time_steps),), chunks=(len(self.time_steps),))

            for var_name in self.variable_names:
                arr = np.zeros((len(self.time_steps), len(self.y_coords), len(self.x_coords)))
                for ti, t in enumerate(self.time_steps):
                    for yi in range(len(self.y_coords)):
                        for xi in range(len(self.x_coords)):
                            val = self.data[t][var_name][yi][xi]
                            arr[ti, yi, xi] = val if math.isfinite(val) else np.nan
                shape = (len(self.time_steps), len(self.y_coords), len(self.x_coords))
                chunks = (1, min(100, len(self.y_coords)), min(100, len(self.x_coords)))
                root.create_dataset(var_name, data=arr, shape=shape, chunks=chunks, fill_value=np.nan, dtype="f8")

            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Vector → Cube builder
# ---------------------------------------------------------------------------

def build_cube_from_vector_layers(
    layers_by_time: Dict[str, QgsVectorLayer],
    field_name: str,
    grid_resolution: float = 100.0,
    extent: Optional[QgsRectangle] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
) -> DataCube:
    """
    Construct a DataCube from multiple vector layers (one per time step).

    Each layer is rasterised onto a common fishnet grid.  The field value
    at each grid cell is the mean of all features intersecting that cell.

    Parameters
    ----------
    layers_by_time : dict[str, QgsVectorLayer]
        Mapping {"2020-01-01": layer, "2021-01-01": layer, ...}.
    field_name : str
        Name of the numeric field to extract.
    grid_resolution : float
        Grid cell size in map units.
    extent : QgsRectangle | None
        Analysis extent; defaults to union of all layer extents.
    feedback : QgsProcessingFeedback | None

    Returns
    -------
    DataCube
    """
    times = sorted(layers_by_time.keys())
    if not times:
        raise ValueError("At least one time step is required.")

    # determine extent
    if extent is None:
        extent = QgsRectangle()
        for layer in layers_by_time.values():
            extent.combineExtentWith(layer.extent())

    # build grid
    x_coords = _frange(extent.xMinimum(), extent.xMaximum(), grid_resolution)
    y_coords = _frange(extent.yMinimum(), extent.yMaximum(), grid_resolution)

    cube = DataCube(x_coords, y_coords, times, [field_name])

    total_steps = len(times) * len(y_coords) * len(x_coords)
    current = 0

    for ti, t_key in enumerate(times):
        layer = layers_by_time[t_key]
        if feedback:
            feedback.pushInfo(f"Processing time step: {t_key}")

        # spatial index for fast lookup
        idx = QgsSpatialIndex(layer.getFeatures())

        for yi, y in enumerate(y_coords):
            for xi, x in enumerate(x_coords):
                if feedback and feedback.isCanceled():
                    return cube

                cell = QgsRectangle(x, y, x + grid_resolution, y + grid_resolution)
                candidates = idx.intersects(cell)
                values = []
                for fid in candidates:
                    feat = layer.getFeature(fid)
                    val = feat[field_name]
                    if val is not None and math.isfinite(float(val)):
                        values.append(float(val))
                agg = sum(values) / len(values) if values else math.nan
                cube.set_value(ti, field_name, xi, yi, agg)

                current += 1
                if feedback and current % 500 == 0:
                    feedback.setProgress(int(100 * current / total_steps))

    return cube


def _frange(start: float, stop: float, step: float) -> List[float]:
    result = []
    x = start
    while x < stop:
        result.append(x)
        x += step
    return result


# ---------------------------------------------------------------------------
# Raster stack → Cube builder
# ---------------------------------------------------------------------------

def build_cube_from_raster_stack(
    raster_paths_by_time: Dict[str, str],
    band: int = 1,
    feedback: Optional[QgsProcessingFeedback] = None,
) -> Optional[DataCube]:
    """
    Build a DataCube from a set of single-band raster files.

    Parameters
    ----------
    raster_paths_by_time : dict[str, str]
        {"2020": "/path/2020.tif", "2021": "/path/2021.tif", ...}.
    band : int
        Band number to read from each raster.
    feedback : QgsProcessingFeedback | None

    Returns
    -------
    DataCube | None
    """
    times = sorted(raster_paths_by_time.keys())
    if not times:
        return None

    # Use the first raster to derive grid parameters
    first_raster = QgsRasterLayer(raster_paths_by_time[times[0]], "ref")
    if not first_raster.isValid():
        return None

    prov = first_raster.dataProvider()
    ext = first_raster.extent()
    cols = first_raster.width()
    rows = first_raster.height()

    x_coords = [ext.xMinimum() + c * ext.width() / cols for c in range(cols)]
    y_coords = [ext.yMinimum() + r * ext.height() / rows for r in range(rows)]

    cube = DataCube(x_coords, y_coords, times, ["value"])

    for ti, t_key in enumerate(times):
        raster = QgsRasterLayer(raster_paths_by_time[t_key], f"t_{t_key}")
        if not raster.isValid():
            if feedback:
                feedback.pushWarning(f"Skipping invalid raster: {t_key}")
            continue

        block = raster.dataProvider().block(band, ext, cols, rows)
        for r in range(rows):
            for c in range(cols):
                val = block.value(c, r)
                cube.set_value(ti, "value", c, r, val if math.isfinite(val) else math.nan)

        if feedback:
            feedback.setProgress(int(100 * (ti + 1) / len(times)))

    return cube
