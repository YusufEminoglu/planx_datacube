# -*- coding: utf-8 -*-
"""Create Data Cube — Processing algorithm."""
from __future__ import annotations

import os
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterEnum,
    QgsProcessingOutputString,
    QgsMapLayer,
    QgsVectorLayer,
    QgsRasterLayer,
)

from ..core.cube_builder import (
    build_cube_from_vector_layers,
    build_cube_from_raster_stack,
    DataCube,
)


class CreateDataCubeAlgorithm(QgsProcessingAlgorithm):
    LAYERS = "LAYERS"
    FIELD = "FIELD"
    GRID_RES = "GRID_RES"
    CUBE_TYPE = "CUBE_TYPE"
    OUTPUT_NC = "OUTPUT_NC"
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
        self.addOutput(
            QgsProcessingOutputString(self.OUTPUT_INFO, "Cube summary")
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.LAYERS, context)
        field = self.parameterAsString(parameters, self.FIELD, context)
        grid_res = self.parameterAsDouble(parameters, self.GRID_RES, context)
        cube_type = self.parameterAsEnum(parameters, self.CUBE_TYPE, context)
        output_nc = self.parameterAsFileOutput(parameters, self.OUTPUT_NC, context)

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

        # store cube in context for downstream algorithms
        # (pass via a temp attribute on the feedback — in production use QgsProcessingContext)
        context.cartolab_cube = cube

        return {self.OUTPUT_INFO: summary}
