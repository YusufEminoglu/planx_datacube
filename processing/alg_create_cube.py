# -*- coding: utf-8 -*-
"""Create Data Cube — Processing algorithm."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterMultipleLayers, QgsProcessingParameterField,
    QgsProcessingParameterNumber, QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination, QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink, QgsProcessingOutputString,
    QgsMapLayer, QgsRectangle, QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from ..core.cube_builder import (
    build_cube_from_vector_layers,
    build_cube_from_raster_stack,
)
from ._help_mixin import DataCubeHelpMixin


class CreateDataCubeAlgorithm(DataCubeHelpMixin, QgsProcessingAlgorithm):
    LAYERS = "LAYERS"
    RASTERS = "RASTERS"
    FIELD = "FIELD"
    GRID_RES = "GRID_RES"
    CUBE_TYPE = "CUBE_TYPE"
    OUTPUT_NC = "OUTPUT_NC"
    OUTPUT_ZARR = "OUTPUT_ZARR"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_PANEL = "OUTPUT_PANEL"
    OUTPUT_INFO = "OUTPUT_INFO"

    TYPES = [("Vector (multi-timestamp layers)", "vector"), ("Raster stack", "raster")]

    def name(self) -> str:
        return "create_data_cube"

    def displayName(self) -> str:
        return "Build Spatiotemporal Data Cube"

    def group(self) -> str:
        return "Data Cube"

    def groupId(self) -> str:
        return "data_cube"

    def createInstance(self):
        return CreateDataCubeAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Construct a multi-dimensional (X×Y×T×V) data cube from vector or "
            "raster time-series layers.\n\n"
            "For vector input: select multiple layers, each representing one "
            "time step. The algorithm rasterises each layer onto a common "
            "fishnet grid and builds the cube.\n\n"
            "For raster input: select multiple single-band rasters in the "
            "separate raster parameter. Their timestamps are taken from the "
            "layer names (sortable strings such as years).\n\n"
            "Output: netCDF4 file (requires netCDF4 Python package) and/or "
            "an optional long-format panel layer that feeds EHSA, Trend, "
            "Anomaly and Forecast directly."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.LAYERS, "Vector layers (one per time step)",
                layerType=QgsProcessing.SourceType.TypeVectorAnyGeometry,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.RASTERS, "Raster layers (one per time step)",
                layerType=QgsProcessing.SourceType.TypeRaster,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(self.FIELD, "Value field (vector input)",
                                        parentLayerParameterName=self.LAYERS,
                                        type=QgsProcessingParameterField.DataType.Numeric,
                                        optional=True)
        )
        self.addParameter(
            QgsProcessingParameterNumber(self.GRID_RES, "Grid cell size (map units)",
                                         type=QgsProcessingParameterNumber.Type.Double,
                                         defaultValue=100.0, minValue=0.01)
        )
        self.addParameter(
            QgsProcessingParameterEnum(self.CUBE_TYPE, "Input type",
                                       options=[t[0] for t in self.TYPES], defaultValue=0)
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_NC, "Output netCDF file",
                fileFilter="NetCDF (*.nc);;All files (*.*)",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_ZARR, "Output Zarr directory store",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_GRID, "Output grid (first time step)",
                type=QgsProcessing.SourceType.TypeVectorPolygon, optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_PANEL, "Long-format panel (analysis-ready)",
                type=QgsProcessing.SourceType.TypeVectorPolygon, optional=True,
            )
        )
        self.addOutput(
            QgsProcessingOutputString(self.OUTPUT_INFO, "Cube summary")
        )

    def processAlgorithm(self, parameters, context, feedback):
        vector_layers = self.parameterAsLayerList(parameters, self.LAYERS, context) or []
        raster_layers = self.parameterAsLayerList(parameters, self.RASTERS, context) or []
        field = self.parameterAsString(parameters, self.FIELD, context)
        grid_res = self.parameterAsDouble(parameters, self.GRID_RES, context)
        cube_type = self.parameterAsEnum(parameters, self.CUBE_TYPE, context)
        output_nc = self.parameterAsFileOutput(parameters, self.OUTPUT_NC, context)
        output_zarr = self.parameterAsFileOutput(parameters, self.OUTPUT_ZARR, context)

        is_raster = self.TYPES[cube_type][1] == "raster"
        if is_raster:
            selected = [lyr for lyr in raster_layers
                        if lyr.type() == QgsMapLayer.LayerType.RasterLayer]
            if len(selected) < 2:
                raise QgsProcessingException(
                    "Select at least 2 raster time-step layers in the "
                    "'Raster layers' parameter.")
            rasters = {lyr.name(): lyr.source() for lyr in selected}
            feedback.pushInfo(f"Building raster cube from {len(rasters)} time steps...")
            cube = build_cube_from_raster_stack(rasters, feedback=feedback)
        else:
            selected = [lyr for lyr in vector_layers
                        if lyr.type() == QgsMapLayer.LayerType.VectorLayer]
            if len(selected) < 2:
                raise QgsProcessingException(
                    "Select at least 2 vector time-step layers.")
            if not field:
                raise QgsProcessingException("A value field is required for vector input.")
            vectors = {lyr.name(): lyr for lyr in selected}
            feedback.pushInfo(f"Building vector cube from {len(vectors)} time steps...")
            cube = build_cube_from_vector_layers(vectors, field, grid_res,
                                                 feedback=feedback)

        if cube is None:
            raise QgsProcessingException("Failed to build data cube.")

        summary = (
            f"Data cube built:\n"
            f"  Input: {'raster stack' if is_raster else 'vector time series'}\n"
            f"  X cells: {len(cube.x_coords)}\n"
            f"  Y cells: {len(cube.y_coords)}\n"
            f"  Time steps: {len(cube.time_steps)}\n"
            f"  Variables: {', '.join(cube.variable_names)}\n"
            f"  Total cells: {len(cube.x_coords) * len(cube.y_coords) * len(cube.time_steps)}"
        )
        feedback.pushInfo(summary)

        if output_nc:
            success = cube.to_netcdf(output_nc)
            if success:
                feedback.pushInfo(f"netCDF exported to: {output_nc}")
            else:
                feedback.pushWarning(
                    "netCDF4 export skipped — Python package 'netCDF4' not available. "
                    "Install with: pip install netCDF4"
                )

        if output_zarr:
            success = cube.to_zarr(output_zarr)
            if success:
                feedback.pushInfo(f"Zarr exported to: {output_zarr}")
            else:
                feedback.pushWarning(
                    "Zarr export skipped — Python package 'zarr' not available. "
                    "Install with: pip install zarr"
                )

        result = {self.OUTPUT_INFO: summary}
        first_layer = selected[0] if selected else None
        crs = first_layer.crs() if first_layer else None

        # Build a grid polygon layer for the first time step.
        if parameters.get(self.OUTPUT_GRID):
            out_fields = QgsFields()
            out_fields.append(QgsField("cell_id", QVariant.Int))
            out_fields.append(QgsField("col", QVariant.Int))
            out_fields.append(QgsField("row", QVariant.Int))
            out_fields.append(QgsField("cell_x", QVariant.Double))
            out_fields.append(QgsField("cell_y", QVariant.Double))
            for var_name in cube.variable_names:
                out_fields.append(QgsField(var_name, QVariant.Double))

            (sink, grid_id) = self.parameterAsSink(
                parameters, self.OUTPUT_GRID, context,
                out_fields, QgsWkbTypes.Type.Polygon, crs,
            )
            if sink:
                t0 = cube.time_steps[0]
                x_coords = cube.x_coords
                y_coords = cube.y_coords
                res_x = cube.x_res or grid_res
                res_y = cube.y_res or grid_res
                total_cells = max(1, len(x_coords) * len(y_coords))
                cell_count = 0
                for yi, y in enumerate(y_coords):
                    for xi, x in enumerate(x_coords):
                        if feedback.isCanceled():
                            break
                        rect = QgsRectangle(x - res_x / 2.0, y - res_y / 2.0,
                                            x + res_x / 2.0, y + res_y / 2.0)
                        geom = QgsGeometry.fromRect(rect)
                        feat = QgsFeature(out_fields)
                        feat.setGeometry(geom)
                        attrs = [yi * len(x_coords) + xi, xi, yi, x, y]
                        for var_name in cube.variable_names:
                            val = cube.data[t0][var_name][yi][xi]
                            attrs.append(val if math.isfinite(val) else None)
                        feat.setAttributes(attrs)
                        sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
                        cell_count += 1
                        if cell_count % 500 == 0 and feedback:
                            feedback.setProgress(int(100 * cell_count / total_cells))
                result[self.OUTPUT_GRID] = grid_id

        # Build a long-format panel so the cube can feed every analysis tool.
        if parameters.get(self.OUTPUT_PANEL):
            panel_fields = QgsFields()
            panel_fields.append(QgsField("cell_id", QVariant.Int))
            panel_fields.append(QgsField("col", QVariant.Int))
            panel_fields.append(QgsField("row", QVariant.Int))
            panel_fields.append(QgsField("time_step", QVariant.Int))
            panel_fields.append(QgsField("time_value", QVariant.Double))
            panel_fields.append(QgsField("value", QVariant.Double))

            (sink, panel_id) = self.parameterAsSink(
                parameters, self.OUTPUT_PANEL, context,
                panel_fields, QgsWkbTypes.Type.Polygon, crs,
            )
            if sink:
                res_x = cube.x_res or grid_res
                res_y = cube.y_res or grid_res
                ncols = len(cube.x_coords)
                written = 0
                total = max(1, len(cube.y_coords) * ncols * len(cube.time_steps))
                for yi, y in enumerate(cube.y_coords):
                    for xi, x in enumerate(cube.x_coords):
                        if feedback.isCanceled():
                            break
                        geom = QgsGeometry.fromRect(QgsRectangle(
                            x - res_x / 2.0, y - res_y / 2.0,
                            x + res_x / 2.0, y + res_y / 2.0))
                        for ti, t_key in enumerate(cube.time_steps):
                            val = cube.data[t_key][cube.variable_names[0]][yi][xi]
                            if not math.isfinite(val):
                                continue
                            feat = QgsFeature(panel_fields)
                            feat.setGeometry(geom)
                            feat.setAttributes([
                                yi * ncols + xi, xi, yi, ti,
                                cube.time_values[ti], round(val, 6),
                            ])
                            sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
                            written += 1
                        if written and written % 500 == 0 and feedback:
                            feedback.setProgress(int(100 * written / total))
                feedback.pushInfo(f"Panel rows written: {written}")
                result[self.OUTPUT_PANEL] = panel_id

        return result
