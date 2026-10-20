# -*- coding: utf-8 -*-
"""
Data Cube Builder — Converts vector/raster time series into a rectangular
space–time cube (X×Y×T×V dimensions).

Supports:
  - Vector layers (polygon/point) with timestamp fields → spatial bins
  - Raster stacks → sampled onto the first raster's reference grid
  - In-memory arrays sized to the selected grid
  - CF-style netCDF4 export and optional Zarr export on disk
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from qgis.core import (
    QgsVectorLayer, QgsRasterLayer,
    QgsRectangle, QgsProcessingFeedback, QgsSpatialIndex, QgsGeometry,
)


# ---------------------------------------------------------------------------
# Small coordinate helpers
# ---------------------------------------------------------------------------

def _sort_time_keys(keys: Sequence[str]) -> List[str]:
    """Sort time labels numerically when possible, lexicographically otherwise."""
    keys = list(keys)
    try:
        return sorted(keys, key=float)
    except (TypeError, ValueError):
        return sorted(keys)


def _time_value(key: str, fallback: float) -> float:
    """Best-effort numeric time coordinate for a layer label."""
    try:
        value = float(key)
    except (TypeError, ValueError):
        return fallback
    return value if math.isfinite(value) else fallback


def _time_values_from_keys(keys: Sequence[str]) -> List[float]:
    """Convert layer labels to a numeric time axis, falling back to indices."""
    return [_time_value(key, float(i)) for i, key in enumerate(keys)]


def _grid_centers(start: float, stop: float, step: float) -> List[float]:
    """Cell centres covering ``start..stop`` with the requested resolution."""
    if step <= 0:
        raise ValueError("Grid resolution must be greater than zero.")
    span = max(0.0, float(stop) - float(start))
    count = max(1, int(math.ceil(span / step - 1e-12)))
    return [start + (i + 0.5) * step for i in range(count)]


def _cell_rect(cx: float, cy: float, x_res: float, y_res: float) -> QgsRectangle:
    """Rectangle centred on a grid cell."""
    return QgsRectangle(cx - x_res / 2.0, cy - y_res / 2.0,
                        cx + x_res / 2.0, cy + y_res / 2.0)


def _safe_var_name(name: str, used: set) -> str:
    """Return a netCDF/Zarr-safe variable name that does not collide."""
    candidate = re.sub(r"[^0-9A-Za-z_]+", "_", str(name or "value")).strip("_")
    if not candidate:
        candidate = "value"
    if candidate[0].isdigit():
        candidate = "v_" + candidate
    reserved = {"x", "y", "time", "crs", "time_label", "x_bnds", "y_bnds"}
    if candidate in reserved:
        candidate = "var_" + candidate
    base = candidate
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


# ---------------------------------------------------------------------------
# Pure-Python lightweight data cube
# ---------------------------------------------------------------------------

class DataCube:
    """
    In-memory multi-dimensional data cube (X×Y×T×V).

    Represented as nested dicts, serialisable to JSON, with optional
    netCDF4 export when the library is available.  ``x_coords`` and
    ``y_coords`` are cell centres; ``x_res``/``y_res`` describe the cell size
    so the netCDF export can also write CF-style bounds.
    """

    def __init__(
        self,
        x_coords: List[float],
        y_coords: List[float],
        time_steps: List[str],
        variable_names: List[str],
        time_values: Optional[List[float]] = None,
        crs_wkt: str = "",
        x_res: Optional[float] = None,
        y_res: Optional[float] = None,
    ):
        self.x_coords = list(x_coords)
        self.y_coords = list(y_coords)
        self.time_steps = list(time_steps)
        self.variable_names = list(variable_names)
        self.time_values = (
            list(time_values)
            if time_values is not None and len(time_values) == len(self.time_steps)
            else _time_values_from_keys(self.time_steps)
        )
        self.crs_wkt = crs_wkt or ""
        self.x_res = float(x_res) if x_res else _infer_resolution(self.x_coords)
        self.y_res = float(y_res) if y_res else _infer_resolution(self.y_coords)

        # data[t][v][y][x] — nested 4D array
        self.data: Dict[str, Dict[str, List[List[float]]]] = {
            t: {v: [[math.nan] * len(self.x_coords) for _ in range(len(self.y_coords))]
                for v in self.variable_names}
            for t in self.time_steps
        }

    # -- accessors -------------------------------------------------------
    def set_value(self, t_idx: int, var: str, x_idx: int, y_idx: int, value: float):
        self.data[self.time_steps[t_idx]][var][y_idx][x_idx] = value

    def get_series(self, x_idx: int, y_idx: int, var: str) -> List[float]:
        """Extract a time series for a single grid cell."""
        return [
            self.data[t][var][y_idx][x_idx]
            for t in self.time_steps
        ]

    @property
    def shape(self) -> Tuple[int, int, int, int]:
        """Return ``(time, variable, y, x)`` dimensions."""
        return (len(self.time_steps), len(self.variable_names),
                len(self.y_coords), len(self.x_coords))

    def finite_values(self, var: str) -> List[float]:
        """All finite values of one variable (used for summaries)."""
        values: List[float] = []
        for t in self.time_steps:
            for row in self.data[t][var]:
                values.extend(v for v in row if math.isfinite(v))
        return values

    # -- export ----------------------------------------------------------
    def to_netcdf(self, path: str) -> bool:
        """Export to netCDF4 if library available."""
        try:
            import netCDF4
            import numpy as np
        except ImportError:
            return False

        ds = netCDF4.Dataset(path, "w", format="NETCDF4")
        try:
            ds.createDimension("time", len(self.time_steps))
            ds.createDimension("y", len(self.y_coords))
            ds.createDimension("x", len(self.x_coords))
            if self.time_steps:
                ds.createDimension(
                    "time_strlen",
                    max(1, max(len(str(t)) for t in self.time_steps)),
                )
            ds.createDimension("bounds", 2)

            x_var = ds.createVariable("x", "f8", ("x",))
            y_var = ds.createVariable("y", "f8", ("y",))
            t_var = ds.createVariable("time", "f8", ("time",))
            x_var[:] = np.asarray(self.x_coords, dtype="f8")
            y_var[:] = np.asarray(self.y_coords, dtype="f8")
            t_var[:] = np.asarray(self.time_values, dtype="f8")
            x_var.units = "map units"
            y_var.units = "map units"
            x_var.long_name = "x coordinate of cell centre"
            y_var.long_name = "y coordinate of cell centre"
            x_var.axis = "X"
            y_var.axis = "Y"
            t_var.units = "time step"
            t_var.long_name = "time coordinate"
            t_var.axis = "T"

            # CF-style bounds make the cube interpretable by GIS readers.
            if self.x_res:
                xb = ds.createVariable("x_bnds", "f8", ("x", "bounds"))
                xb[:, 0] = np.asarray(self.x_coords) - self.x_res / 2.0
                xb[:, 1] = np.asarray(self.x_coords) + self.x_res / 2.0
                x_var.bounds = "x_bnds"
            if self.y_res:
                yb = ds.createVariable("y_bnds", "f8", ("y", "bounds"))
                yb[:, 0] = np.asarray(self.y_coords) - self.y_res / 2.0
                yb[:, 1] = np.asarray(self.y_coords) + self.y_res / 2.0
                y_var.bounds = "y_bnds"

            labels = ds.createVariable("time_label", "S1",
                                       ("time", "time_strlen"))
            raw = np.full((len(self.time_steps), ds.dimensions["time_strlen"].size),
                          b" ", dtype="S1")
            for ti, label in enumerate(self.time_steps):
                encoded = str(label).encode("utf-8")[:raw.shape[1]]
                raw[ti, :len(encoded)] = np.frombuffer(encoded, dtype="S1")
            labels[:] = raw

            if self.crs_wkt:
                crs = ds.createVariable("crs", "i4")
                crs.crs_wkt = self.crs_wkt
                crs.long_name = "coordinate reference system"
                crs.grid_mapping_name = "unknown"

            used: set = set()
            for var_name in self.variable_names:
                safe = _safe_var_name(var_name, used)
                arr = np.zeros((len(self.time_steps), len(self.y_coords),
                                len(self.x_coords)), dtype="f8")
                for ti, t in enumerate(self.time_steps):
                    for yi in range(len(self.y_coords)):
                        for xi in range(len(self.x_coords)):
                            val = self.data[t][var_name][yi][xi]
                            arr[ti, yi, xi] = val if math.isfinite(val) else np.nan
                var = ds.createVariable(safe, "f8", ("time", "y", "x"),
                                        fill_value=np.nan, zlib=True,
                                        complevel=4)
                var[:] = arr
                var.long_name = str(var_name)
                var.coordinates = "time y x"
                if self.crs_wkt:
                    var.grid_mapping = "crs"

            ds.Conventions = "CF-1.8"
            ds.title = "PlanX DataCube Lab data cube"
            ds.source = "PlanX DataCube Lab"
            ds.summary = (
                f"{len(self.time_steps)} time steps, "
                f"{len(self.y_coords)} rows, {len(self.x_coords)} columns, "
                f"{len(self.variable_names)} variable(s)"
            )
        finally:
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

            root.create_dataset("x", data=np.array(self.x_coords, dtype="f8"),
                                shape=(len(self.x_coords),),
                                chunks=(len(self.x_coords),))
            root.create_dataset("y", data=np.array(self.y_coords, dtype="f8"),
                                shape=(len(self.y_coords),),
                                chunks=(len(self.y_coords),))
            root.create_dataset("time", data=np.array(self.time_values, dtype="f8"),
                                shape=(len(self.time_steps),),
                                chunks=(len(self.time_steps),))
            root.attrs["Conventions"] = "CF-1.8"
            root.attrs["source"] = "PlanX DataCube Lab"
            if self.crs_wkt:
                root.attrs["crs_wkt"] = self.crs_wkt

            used: set = set()
            for var_name in self.variable_names:
                safe = _safe_var_name(var_name, used)
                arr = np.zeros((len(self.time_steps), len(self.y_coords),
                                len(self.x_coords)), dtype="f8")
                for ti, t in enumerate(self.time_steps):
                    for yi in range(len(self.y_coords)):
                        for xi in range(len(self.x_coords)):
                            val = self.data[t][var_name][yi][xi]
                            arr[ti, yi, xi] = val if math.isfinite(val) else np.nan
                shape = (len(self.time_steps), len(self.y_coords),
                         len(self.x_coords))
                chunks = (1, min(100, len(self.y_coords)),
                          min(100, len(self.x_coords)))
                root.create_dataset(safe, data=arr, shape=shape, chunks=chunks,
                                    fill_value=np.nan, dtype="f8")
            return True
        except Exception:
            return False


def _infer_resolution(coords: Sequence[float]) -> float:
    """Infer a positive cell size from coordinate spacing."""
    if len(coords) < 2:
        return 0.0
    gaps = [abs(float(coords[i + 1]) - float(coords[i]))
            for i in range(len(coords) - 1)]
    gaps = [g for g in gaps if g > 0]
    return min(gaps) if gaps else 0.0


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
    at each grid cell is the mean of all features whose geometry intersects
    that cell.  Empty cells stay NaN.

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
    times = _sort_time_keys(layers_by_time.keys())
    if not times:
        raise ValueError("At least one time step is required.")
    if grid_resolution <= 0:
        raise ValueError("Grid resolution must be greater than zero.")

    # Determine extent
    if extent is None:
        extent = QgsRectangle()
        for layer in layers_by_time.values():
            extent.combineExtentWith(layer.extent())

    if extent.isNull() or extent.width() < 0 or extent.height() < 0:
        raise ValueError("The input layers have no valid extent.")

    # Build grid (cell centres)
    x_coords = _grid_centers(extent.xMinimum(), extent.xMaximum(), grid_resolution)
    y_coords = _grid_centers(extent.yMinimum(), extent.yMaximum(), grid_resolution)

    first_layer = layers_by_time[times[0]]
    crs_wkt = first_layer.crs().toWkt() if first_layer.crs().isValid() else ""
    cube = DataCube(
        x_coords, y_coords, times, [field_name],
        time_values=_time_values_from_keys(times),
        crs_wkt=crs_wkt,
        x_res=grid_resolution,
        y_res=grid_resolution,
    )

    total_steps = max(1, len(times) * len(y_coords) * len(x_coords))
    current = 0

    for ti, t_key in enumerate(times):
        layer = layers_by_time[t_key]
        if feedback:
            feedback.pushInfo(f"Processing time step: {t_key}")

        # Cache features and build a spatial index once per time step.
        index = QgsSpatialIndex()
        features: Dict[int, object] = {}
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            raw = feat[field_name]
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            index.addFeature(feat)
            features[feat.id()] = feat

        for yi, cy in enumerate(y_coords):
            for xi, cx in enumerate(x_coords):
                if feedback and feedback.isCanceled():
                    return cube

                rect = _cell_rect(cx, cy, grid_resolution, grid_resolution)
                cell_geom = QgsGeometry.fromRect(rect)
                values: List[float] = []
                for fid in index.intersects(rect):
                    feat = features.get(fid)
                    if feat is None:
                        continue
                    geom = feat.geometry()
                    if geom is None or not geom.intersects(cell_geom):
                        continue
                    try:
                        value = float(feat[field_name])
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(value):
                        values.append(value)
                agg = sum(values) / len(values) if values else math.nan
                cube.set_value(ti, field_name, xi, yi, agg)

                current += 1
                if feedback and current % 250 == 0:
                    feedback.setProgress(int(100 * current / total_steps))

    return cube


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

    The first raster defines the reference grid.  Every other raster is
    sampled onto that grid; rasters in a different CRS are skipped with a
    warning instead of silently producing misaligned values.

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
    times = _sort_time_keys(raster_paths_by_time.keys())
    if not times:
        return None

    # Use the first raster to derive grid parameters
    first_raster = QgsRasterLayer(raster_paths_by_time[times[0]], "ref")
    if not first_raster.isValid():
        return None

    ext = first_raster.extent()
    cols = first_raster.width()
    rows = first_raster.height()
    if cols < 1 or rows < 1:
        return None

    x_res = ext.width() / cols
    y_res = ext.height() / rows
    x_coords = [ext.xMinimum() + (c + 0.5) * x_res for c in range(cols)]
    y_coords = [ext.yMinimum() + (r + 0.5) * y_res for r in range(rows)]

    ref_crs = first_raster.crs()
    cube = DataCube(
        x_coords, y_coords, times, ["value"],
        time_values=_time_values_from_keys(times),
        crs_wkt=ref_crs.toWkt() if ref_crs.isValid() else "",
        x_res=x_res,
        y_res=y_res,
    )

    for ti, t_key in enumerate(times):
        raster = QgsRasterLayer(raster_paths_by_time[t_key], f"t_{t_key}")
        if not raster.isValid():
            if feedback:
                feedback.pushWarning(f"Skipping invalid raster: {t_key}")
            continue
        if ref_crs.isValid() and raster.crs().isValid() and raster.crs() != ref_crs:
            if feedback:
                feedback.pushWarning(
                    f"Skipping {t_key}: raster CRS differs from the reference "
                    f"raster ({raster.crs().authid()} vs {ref_crs.authid()}).")
            continue

        # QGIS' block reader can leave the last row/column of an exact-extent
        # request uninitialised (the right/bottom edge is exclusive).  Read one
        # pixel beyond the reference grid and slice the valid centre back out.
        pad_x = x_res if x_res > 0 else 1.0
        pad_y = y_res if y_res > 0 else 1.0
        read_ext = QgsRectangle(
            ext.xMinimum() - pad_x, ext.yMinimum() - pad_y,
            ext.xMaximum() + pad_x, ext.yMaximum() + pad_y,
        )
        block = raster.dataProvider().block(
            band, read_ext, cols + 4, rows + 4)
        if block is None:
            if feedback:
                feedback.pushWarning(f"Could not read raster: {t_key}")
            continue

        for r in range(rows):
            for c in range(cols):
                if feedback and feedback.isCanceled():
                    return cube
                bc, br = c + 1, r + 1
                if block.isNoData(bc, br):
                    value = math.nan
                else:
                    value = float(block.value(bc, br))
                    if not math.isfinite(value):
                        value = math.nan
                cube.set_value(ti, "value", c, r, value)

        if feedback:
            feedback.pushInfo(f"Read raster time step: {t_key}")
            feedback.setProgress(int(100 * (ti + 1) / len(times)))

    return cube
