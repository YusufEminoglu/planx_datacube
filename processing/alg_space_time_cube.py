# -*- coding: utf-8 -*-
"""Space-Time Cube Aggregation — bin events into a fishnet × time panel."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingParameterEnum, QgsProcessingParameterBoolean,
    QgsProcessingParameterFileDestination, QgsProcessingOutputString,
    QgsRectangle, QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from ..core.panel import centroid_xy
from ..core.cube_builder import DataCube
from ._help_mixin import DataCubeHelpMixin

MAX_PANEL_FEATURES = 3_000_000


class SpaceTimeCubeAlgorithm(DataCubeHelpMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    AGG = "AGG"
    GRID_SIZE = "GRID_SIZE"
    TIME_STEP = "TIME_STEP"
    DROP_EMPTY = "DROP_EMPTY"
    OUTPUT = "OUTPUT"
    OUTPUT_NC = "OUTPUT_NC"
    OUTPUT_INFO = "OUTPUT_INFO"

    AGG_MODES = [
        ("Count", "count"),
        ("Sum", "sum"),
        ("Mean", "mean"),
        ("Maximum", "max"),
        ("Minimum", "min"),
    ]

    def name(self) -> str:
        return "space_time_cube"

    def displayName(self) -> str:
        return "Space-Time Cube Aggregation"

    def group(self) -> str:
        return "Data Cube"

    def groupId(self) -> str:
        return "data_cube"

    def createInstance(self):
        return SpaceTimeCubeAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Aggregate point/feature events into a regular space-time cube: a "
            "fishnet grid crossed with time bins.\n\n"
            "Each feature is binned by its centroid into a grid cell and by its "
            "time field into a time step, then aggregated (count of events, or "
            "sum/mean/max/min of a value field).\n\n"
            "The output is a long-format panel polygon layer — one row per grid "
            "cell per time step (fields cell_id, col, row, time_step, "
            "time_value, value, count) — that feeds directly into Emerging Hot "
            "Spot Analysis, Temporal Trend, Anomaly and Forecast tools "
            "(ID = cell_id, Time = time_step, Value = value).\n\n"
            "Optionally writes the cube to netCDF4 for voxel rendering."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, "Input events layer", [QgsProcessing.SourceType.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.TIME_FIELD, "Time field (numeric)", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterField(
            self.VALUE_FIELD, "Value field (leave empty to count events)",
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.DataType.Numeric, optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.AGG, "Aggregation", options=[a[0] for a in self.AGG_MODES], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.GRID_SIZE, "Grid cell size (map units)",
            type=QgsProcessingParameterNumber.Type.Double, defaultValue=1000.0, minValue=1e-6))
        self.addParameter(QgsProcessingParameterNumber(
            self.TIME_STEP, "Time step size (0 = one bin per distinct time value)",
            type=QgsProcessingParameterNumber.Type.Double, defaultValue=0.0, minValue=0.0,
            optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DROP_EMPTY, "Keep only grid cells that contain data", defaultValue=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Space-time panel",
            type=QgsProcessing.SourceType.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_NC, "Output netCDF cube (optional)",
            fileFilter="NetCDF (*.nc);;All files (*.*)", optional=True, createByDefault=False))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_INFO, "Cube summary"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        agg_mode = self.AGG_MODES[self.parameterAsEnum(parameters, self.AGG, context)][1]
        grid_size = self.parameterAsDouble(parameters, self.GRID_SIZE, context)
        time_step = self.parameterAsDouble(parameters, self.TIME_STEP, context)
        drop_empty = self.parameterAsBool(parameters, self.DROP_EMPTY, context)
        output_nc = self.parameterAsFileOutput(parameters, self.OUTPUT_NC, context)

        if agg_mode != "count" and not value_field:
            raise QgsProcessingException(
                "A value field is required for sum/mean/max/min aggregation "
                "(only 'Count' works without one).")

        # ---- pass 1: read events (centroid, time, value) --------------------
        events = []  # (x, y, t, v)
        for feat in source.getFeatures():
            raw_t = feat[time_field]
            if raw_t is None:
                continue
            try:
                t = float(raw_t)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(t):
                continue
            xy = centroid_xy(feat.geometry())
            if xy is None:
                continue
            if value_field:
                raw_v = feat[value_field]
                try:
                    v = float(raw_v)
                except (ValueError, TypeError):
                    continue
                if not math.isfinite(v):
                    continue
            else:
                v = 1.0
            events.append((xy[0], xy[1], t, v))

        if not events:
            raise QgsProcessingException("No events with a valid time and geometry were found.")

        xs = [e[0] for e in events]
        ys = [e[1] for e in events]
        ts = [e[2] for e in events]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        t_min, t_max = min(ts), max(ts)

        # +1 so a point sitting exactly on the far edge gets its own column
        # (avoids merging the last cell into the previous one).
        ncols = max(1, int((x_max - x_min) / grid_size) + 1)
        nrows = max(1, int((y_max - y_min) / grid_size) + 1)

        # ---- time bins ------------------------------------------------------
        if time_step and time_step > 0:
            ntimes = max(1, int(math.floor((t_max - t_min) / time_step)) + 1)
            time_values = [t_min + b * time_step for b in range(ntimes)]

            def time_bin(t):
                return min(ntimes - 1, max(0, int(math.floor((t - t_min) / time_step))))
        else:
            distinct = sorted(set(ts))
            time_values = [float(v) for v in distinct]
            ntimes = len(distinct)
            index_of = {v: i for i, v in enumerate(distinct)}

            def time_bin(t):
                return index_of[t]

        est = ncols * nrows * ntimes
        feedback.pushInfo(
            f"Grid {ncols} x {nrows} cells, {ntimes} time steps "
            f"({len(events)} events). Full cube = {est} cells.")
        if est > MAX_PANEL_FEATURES and not drop_empty:
            raise QgsProcessingException(
                f"Full cube would be {est} features (> {MAX_PANEL_FEATURES}). "
                "Increase the grid cell size, widen the time step, or enable "
                "'Keep only grid cells that contain data'.")

        # ---- aggregate ------------------------------------------------------
        # acc[(col,row,bin)] = [count, sum, max, min]
        acc: dict = {}
        cells_with_data: set = set()
        for x, y, t, v in events:
            col = min(ncols - 1, max(0, int((x - x_min) / grid_size)))
            row = min(nrows - 1, max(0, int((y - y_min) / grid_size)))
            b = time_bin(t)
            cells_with_data.add((col, row))
            key = (col, row, b)
            rec = acc.get(key)
            if rec is None:
                acc[key] = [1, v, v, v]
            else:
                rec[0] += 1
                rec[1] += v
                if v > rec[2]:
                    rec[2] = v
                if v < rec[3]:
                    rec[3] = v

        def aggregate(rec):
            """rec = [count, sum, max, min] -> (value, count)."""
            if rec is None:
                return (0.0 if agg_mode in ("count", "sum") else None), 0
            cnt, ssum, smax, smin = rec
            if agg_mode == "count":
                return float(cnt), cnt
            if agg_mode == "sum":
                return ssum, cnt
            if agg_mode == "max":
                return smax, cnt
            if agg_mode == "min":
                return smin, cnt
            return (ssum / cnt if cnt else None), cnt  # mean

        # ---- output panel ---------------------------------------------------
        out_fields = QgsFields()
        out_fields.append(QgsField("cell_id", QVariant.Int))
        out_fields.append(QgsField("col", QVariant.Int))
        out_fields.append(QgsField("row", QVariant.Int))
        out_fields.append(QgsField("time_step", QVariant.Int))
        out_fields.append(QgsField("time_value", QVariant.Double))
        out_fields.append(QgsField("value", QVariant.Double))
        out_fields.append(QgsField("count", QVariant.Int))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, QgsWkbTypes.Type.Polygon, source.sourceCrs())

        if drop_empty:
            target_cells = sorted(cells_with_data)
        else:
            target_cells = [(c, r) for r in range(nrows) for c in range(ncols)]

        feedback.pushInfo(
            f"Emitting {len(target_cells) * ntimes} panel rows "
            f"({len(target_cells)} cells x {ntimes} steps).")

        written = 0
        total = max(1, len(target_cells))
        for idx, (col, row) in enumerate(target_cells):
            if feedback.isCanceled():
                break
            cell_id = row * ncols + col
            cx0 = x_min + col * grid_size
            cy0 = y_min + row * grid_size
            geom = QgsGeometry.fromRect(
                QgsRectangle(cx0, cy0, cx0 + grid_size, cy0 + grid_size))
            for b in range(ntimes):
                value, cnt = aggregate(acc.get((col, row, b)))
                feat = QgsFeature(out_fields)
                feat.setGeometry(geom)
                feat.setAttributes([
                    cell_id, col, row, b, round(time_values[b], 6),
                    round(value, 6) if value is not None else None, cnt,
                ])
                sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
                written += 1
            feedback.setProgress(int(100 * idx / total))

        summary = (
            f"Space-time cube: {ncols}x{nrows} grid, {ntimes} time steps, "
            f"{len(target_cells)} populated cells, {written} panel rows "
            f"({agg_mode} aggregation)."
        )
        feedback.pushInfo(summary)

        # ---- optional netCDF cube (full regular grid) -----------------------
        if output_nc:
            try:
                x_centers = [x_min + (c + 0.5) * grid_size for c in range(ncols)]
                y_centers = [y_min + (r + 0.5) * grid_size for r in range(nrows)]
                cube = DataCube(x_centers, y_centers,
                                [str(tv) for tv in time_values], ["value"])
                for (col, row, b), rec in acc.items():
                    value, _cnt = aggregate(rec)
                    if value is not None:
                        cube.set_value(b, "value", col, row, value)
                if cube.to_netcdf(output_nc):
                    feedback.pushInfo(f"netCDF cube written to: {output_nc}")
                else:
                    feedback.pushWarning(
                        "netCDF export skipped — Python package 'netCDF4' not available.")
            except Exception as exc:
                feedback.pushWarning(f"netCDF export failed: {exc}")

        return {self.OUTPUT: dest_id, self.OUTPUT_INFO: summary}
