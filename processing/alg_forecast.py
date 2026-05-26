# -*- coding: utf-8 -*-
"""Time-Series Forecast — Processing algorithm."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeatureSink,
    QgsFeature,
    QgsField,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from ..core.forecasting_studio import forecast_cell_series


class ForecastAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    STEPS_AHEAD = "STEPS_AHEAD"
    METHOD = "METHOD"
    OUTPUT = "OUTPUT"

    METHODS = [
        ("Auto (ARIMA → Random Forest → Exponential)", "auto"),
        ("ARIMA", "arima"),
        ("Random Forest", "random_forest"),
        ("Exponential Smoothing", "exponential"),
    ]

    def name(self) -> str:
        return "time_series_forecast"

    def displayName(self) -> str:
        return "Time-Series Forecast (ARIMA / RF / ES)"

    def group(self) -> str:
        return "Spatiotemporal Analysis"

    def groupId(self) -> str:
        return "spatiotemporal_analysis"

    def createInstance(self):
        return ForecastAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Forecast future values for each spatial unit using the selected "
            "time-series method.\n\n"
            "Each unique location ID's value series is modelled independently. "
            "Auto mode tries ARIMA first, falls back to Random Forest, then "
            "exponential smoothing.\n\n"
            "Output contains one row per location with geometry, forecast values, "
            "and the method actually used."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, "Input panel data layer",
                [QgsProcessing.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(self.ID_FIELD, "Location ID field",
                                         parentLayerParameterName=self.INPUT)
        )
        self.addParameter(
            QgsProcessingParameterField(self.TIME_FIELD, "Time step field (numeric)",
                                         parentLayerParameterName=self.INPUT,
                                         type=QgsProcessingParameterField.Numeric)
        )
        self.addParameter(
            QgsProcessingParameterField(self.VALUE_FIELD, "Value field to forecast",
                                         parentLayerParameterName=self.INPUT,
                                         type=QgsProcessingParameterField.Numeric)
        )
        self.addParameter(
            QgsProcessingParameterNumber(self.STEPS_AHEAD, "Forecast steps ahead",
                                          type=QgsProcessingParameterNumber.Integer,
                                          defaultValue=5, minValue=1, maxValue=50)
        )
        self.addParameter(
            QgsProcessingParameterEnum(self.METHOD, "Forecast method",
                                        options=[m[0] for m in self.METHODS], defaultValue=0)
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, "Forecast output")
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        steps_ahead = self.parameterAsInt(parameters, self.STEPS_AHEAD, context)
        method_idx = self.parameterAsEnum(parameters, self.METHOD, context)
        method = self.METHODS[method_idx][1]

        # organise data
        loc_series: dict = {}
        loc_geom: dict = {}
        for feat in source.getFeatures():
            loc_id = feat[id_field]
            t = int(float(feat[time_field]))
            val = feat[value_field]
            if val is None or not math.isfinite(float(val)):
                continue
            loc_series.setdefault(loc_id, {})[t] = float(val)
            if loc_id not in loc_geom:
                g = feat.geometry()
                if g and not g.isEmpty():
                    loc_geom[loc_id] = g

        if not loc_series:
            raise QgsProcessingException("No valid data found.")

        # Build output fields
        out_fields = source.fields()
        for s in range(1, steps_ahead + 1):
            out_fields.append(QgsField(f"forecast_t+{s}", QVariant.Double))
        out_fields.append(QgsField("forecast_method", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs(),
        )

        total = len(loc_series)
        for i, (loc_id, time_map) in enumerate(loc_series.items()):
            if feedback.isCanceled():
                break

            # sort by time and extract series
            sorted_times = sorted(time_map.keys())
            series = [time_map[t] for t in sorted_times]

            forecast, used_method = forecast_cell_series(series, method, steps_ahead)

            feat = QgsFeature()
            feat.setGeometry(loc_geom.get(loc_id, source.getFeature(0).geometry()))
            attrs = [loc_id] + forecast + [used_method]
            feat.setAttributes(attrs)
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / total))

        feedback.pushInfo(f"Forecast complete: {total} locations, {steps_ahead} steps ahead.")
        return {self.OUTPUT: dest_id}
