# -*- coding: utf-8 -*-
"""Create Data Cube — Processing algorithm."""
from __future__ import annotations

import os
import math

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsPointXY, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterMultipleLayers, QgsProcessingParameterField,
    QgsProcessingParameterNumber, QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination, QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink, QgsProcessingOutputString,
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer, QgsRectangle, QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from ..core.cube_builder import (
    build_cube_from_vector_layers,
    build_cube_from_raster_stack,
    DataCube,
)
from ._help_mixin import DataCubeHelpMixin


class CreateDataCubeAlgorithm(DataCubeHelpMixin, QgsProcessingAlgorithm):
    LAYERS = "LAYERS"
    FIELD = "FIELD"
    GRID_RES = "GRID_RES"
    CUBE_TYPE = "CUBE_TYPE"
    OUTPUT_NC = "OUTPUT_NC"
    OUTPUT_ZARR = "OUTPUT_ZARR"
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
            "For raster input: select multiple single-band rasters. Their "
            "timestamps are taken from the layer names (sortable strings).\n\n"
            "Output: netCDF4 file (requires netCDF4 Python package) and/or "
            "in-memory cube for downstream EHSA / forecasting."
        )

    OUTPUT_GRID = "OUTPUT_GRID"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.LAYERS, "Input layers (one per time step)",
                layerType=QgsProcessing.SourceType.TypeVectorAnyGeometry,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(self.FIELD, "Value field",
                                         parentLayerParameterName=self.LAYERS,
                                         type=QgsProcessingParameterField.Numeric,
                                         optional=True)
        )
        self.addParameter(
            QgsProcessingParameterNumber(self.GRID_RES, "Grid cell size (map units)",
                                          type=QgsProcessingParameterNumber.Double,
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
        self.addOutput(
            QgsProcessingOutputString(self.OUTPUT_INFO, "Cube summary")
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.LAYERS, context)
        field = self.parameterAsString(parameters, self.FIELD, context)
        grid_res = self.parameterAsDouble(parameters, self.GRID_RES, context)
        cube_type = self.parameterAsEnum(parameters, self.CUBE_TYPE, context)
        output_nc = self.parameterAsFileOutput(parameters, self.OUTPUT_NC, context)
        output_zarr = self.parameterAsFileOutput(parameters, self.OUTPUT_ZARR, context)

        if len(layers) < 2:
            raise QgsProcessingException("At least 2 time-step layers are required.")

        feedback.pushInfo(f"Building cube from {len(layers)} time steps...")

        if self.TYPES[cube_type][1] == "raster":
            rasters = {lyr.name(): lyr.source() for lyr in layers
                       if lyr.type() == QgsMapLayer.RasterLayer}
            cube = build_cube_from_raster_stack(rasters, feedback=feedback)
        else:
            vectors = {lyr.name(): lyr for lyr in layers
                       if lyr.type() == QgsMapLayer.VectorLayer}
            if not field:
                raise QgsProcessingException("A value field is required for vector input.")
            cube = build_cube_from_vector_layers(vectors, field, grid_res, feedback=feedback)

        if cube is None:
            raise QgsProcessingException("Failed to build data cube.")

        summary = (
            f"Data cube built:\n"
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

        # Build grid polygon layer for the first time step
        result = {self.OUTPUT_INFO: summary}

        if parameters.get(self.OUTPUT_GRID):
            # determine CRS from first layer
            crs = layers[0].crs() if layers else None
            out_fields = QgsFields()
            out_fields.append(QgsField("cell_x", QVariant.Double))
            out_fields.append(QgsField("cell_y", QVariant.Double))
            for var_name in cube.variable_names:
                out_fields.append(QgsField(var_name, QVariant.Double))

            (sink, grid_id) = self.parameterAsSink(
                parameters, self.OUTPUT_GRID, context,
                out_fields, QgsWkbTypes.Polygon, crs,
            )
            if sink:
                t0 = cube.time_steps[0]
                x_coords = cube.x_coords
                y_coords = cube.y_coords
                res_x = x_coords[1] - x_coords[0] if len(x_coords) > 1 else grid_res
                res_y = y_coords[1] - y_coords[0] if len(y_coords) > 1 else grid_res
                total_cells = len(x_coords) * len(y_coords)
                cell_count = 0
                for yi, y in enumerate(y_coords):
                    for xi, x in enumerate(x_coords):
                        if feedback.isCanceled():
                            break
                        rect = QgsRectangle(x, y, x + res_x, y + res_y)
                        geom = QgsGeometry.fromRect(rect)
                        feat = QgsFeature(out_fields)
                        feat.setGeometry(geom)
                        attrs = [x, y]
                        for var_name in cube.variable_names:
                            val = cube.data[t0][var_name][yi][xi]
                            attrs.append(val if math.isfinite(val) else None)
                        feat.setAttributes(attrs)
                        sink.addFeature(feat, QgsFeatureSink.FastInsert)
                        cell_count += 1
                        if cell_count % 500 == 0 and feedback:
                            feedback.setProgress(int(100 * cell_count / total_cells))
                result[self.OUTPUT_GRID] = grid_id

        return result
