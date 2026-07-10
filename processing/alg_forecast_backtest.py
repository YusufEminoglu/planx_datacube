# -*- coding: utf-8 -*-
"""Forecast Backtest — hold-out accuracy comparison of forecast methods."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QVariant

from ..core.forecasting_studio import backtest_series, BACKTEST_METHODS
from ..core.panel import read_panel
from .symbology import attach_categorized_symbology
from ._help_mixin import DataCubeHelpMixin


def _round(v):
    return round(v, 6) if isinstance(v, float) and math.isfinite(v) else None


class ForecastBacktestAlgorithm(DataCubeHelpMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    HOLDOUT = "HOLDOUT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "forecast_backtest"

    def displayName(self) -> str:
        return "Forecast Backtest (hold-out accuracy)"

    def group(self) -> str:
        return "Spatiotemporal Analysis"

    def groupId(self) -> str:
        return "spatiotemporal_analysis"

    def createInstance(self):
        return ForecastBacktestAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Backtest the forecasting methods per location: hold out the last "
            "N observations, forecast them from the earlier history, and score "
            "each method by MAE, RMSE and MAPE.\n\n"
            "The method with the lowest hold-out RMSE is reported as best_method "
            "— use it to decide which method to trust before forecasting "
            "forward with the Time-Series Forecast tool.\n\n"
            "Output: location_id, n_obs, best_method, best_rmse, and per-method "
            "RMSE columns (exponential / ARIMA / random forest)."
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
            self.VALUE_FIELD, "Value field", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterNumber(
            self.HOLDOUT, "Hold-out length (steps)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=3, minValue=1, maxValue=50))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Backtest output"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        holdout = self.parameterAsInt(parameters, self.HOLDOUT, context)

        panel = read_panel(source, id_field, time_field, value_field)
        if panel.n_locations < 1:
            raise QgsProcessingException("No valid panel data found.")

        feedback.pushInfo(
            f"Backtest: {panel.n_locations} locations, hold-out {holdout} steps")

        out_fields = QgsFields()
        out_fields.append(QgsField("location_id", QVariant.String))
        out_fields.append(QgsField("n_obs", QVariant.Int))
        out_fields.append(QgsField("n_test", QVariant.Int))
        out_fields.append(QgsField("best_method", QVariant.String))
        out_fields.append(QgsField("best_rmse", QVariant.Double))
        out_fields.append(QgsField("best_mae", QVariant.Double))
        out_fields.append(QgsField("best_mape", QVariant.Double))
        # one RMSE column per candidate method
        method_keys = ["exponential_smoothing", "ARIMA", "RandomForest"]
        for mk in method_keys:
            out_fields.append(QgsField(f"rmse_{mk[:10].lower()}", QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs())

        total = panel.n_locations
        evaluated = 0
        best_counts: dict = {}
        for i, loc in enumerate(panel.locations):
            if feedback.isCanceled():
                break
            series = panel.raw_series(loc)
            bt = backtest_series(series, holdout=holdout, methods=BACKTEST_METHODS)
            best = bt["best_method"]
            best_counts[best] = best_counts.get(best, 0) + 1
            if best != "none":
                evaluated += 1

            scores = bt["scores"]
            best_mae = best_rmse = best_mape = None
            if best in scores:
                mae, rmse, mape = scores[best]
                best_mae, best_rmse, best_mape = _round(mae), _round(rmse), _round(mape)

            row = [loc, len(series), bt["n_test"], best, best_rmse, best_mae, best_mape]
            for mk in method_keys:
                if mk in scores:
                    row.append(_round(scores[mk][1]))  # rmse
                else:
                    row.append(None)

            feat = QgsFeature(out_fields)
            feat.setGeometry(panel.loc_geom.get(loc, QgsGeometry()))
            feat.setAttributes(row)
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / total))

        summary = ", ".join(f"{m}: {c}" for m, c in sorted(best_counts.items()))
        feedback.pushInfo(f"Backtested {evaluated}/{total} locations. Best-method tally — {summary}")

        attach_categorized_symbology(
            context, dest_id, self.OUTPUT, "best_method",
            [("exponential_smoothing", "#66c2a5", "Exponential smoothing"),
             ("ARIMA", "#fc8d62", "ARIMA"),
             ("RandomForest", "#8da0cb", "Random forest"),
             ("none", "#e8e8e8", "Too short to backtest")],
            feedback)

        return {self.OUTPUT: dest_id}
