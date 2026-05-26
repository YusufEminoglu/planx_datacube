# -*- coding: utf-8 -*-
"""Time-Series Forecast — Processing algorithm."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
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
        ("Auto (ARIMA -> RF -> Exponential)", "auto"),
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
            "Forecast future values per location using the selected method.\n\n"
            "Auto mode tries ARIMA first, then Random Forest, then Exponential "
            "Smoothing. Output: one row per location with forecast columns "
            "and the method actually used."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, "Input panel data layer", [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD, "Location ID field", parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterField(
            self.TIME_FIELD, "Time step field (numeric)", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterField(
            self.VALUE_FIELD, "Value field to forecast", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterNumber(
            self.STEPS_AHEAD, "Forecast steps ahead",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=5, minValue=1, maxValue=50))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, "Forecast method",
            options=[m[0] for m in self.METHODS], defaultValue=0))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Forecast output"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        steps_ahead = self.parameterAsInt(parameters, self.STEPS_AHEAD, context)
        method_idx = self.parameterAsEnum(parameters, self.METHOD, context)
        method = self.METHODS[method_idx][1]

        # Organise: {loc_id: {time: value}}
        loc_series: dict = {}
        loc_geom = {}
        for feat in source.getFeatures():
            loc_id = str(feat[id_field])
            raw_t = feat[time_field]
            raw_v = feat[value_field]
            if raw_t is None or raw_v is None:
                continue
            try:
                t = int(float(raw_t))
                v = float(raw_v)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(v):
                continue
            loc_series.setdefault(loc_id, {})[t] = v
            if loc_id not in loc_geom:
                g = feat.geometry()
                if g and not g.isEmpty():
                    loc_geom[loc_id] = g

        if not loc_series:
            raise QgsProcessingException("No valid panel data found.")

        # Build output schema: location_id + forecast columns + method
        out_fields = QgsFields()
        out_fields.append(QgsField("location_id", QVariant.String))
        for s in range(1, steps_ahead + 1):
            out_fields.append(QgsField(f"forecast_t{s}", QVariant.Double))
        out_fields.append(QgsField("forecast_method", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs(),
        )

        total = len(loc_series)
        for i, (loc_id, time_map) in enumerate(loc_series.items()):
            if feedback.isCanceled():
                break
            sorted_times = sorted(time_map.keys())
            series = [time_map[t] for t in sorted_times]

            forecast, used_method = forecast_cell_series(series, method, steps_ahead)

            feat = QgsFeature(out_fields)
            feat.setGeometry(loc_geom.get(loc_id, QgsGeometry()))
            attrs = [str(loc_id)] + [round(float(v), 6) for v in forecast] + [str(used_method)]
            feat.setAttributes(attrs)
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / total))

        feedback.pushInfo(f"Forecast complete: {total} locations, {steps_ahead} steps ahead.")
        return {self.OUTPUT: dest_id}
