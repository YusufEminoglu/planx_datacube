# -*- coding: utf-8 -*-
"""Temporal Trend Analysis — Mann-Kendall + Theil-Sen per location."""
from __future__ import annotations

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QVariant

from ..core.statistics_ehsa import mann_kendall_test
from ..core.timeseries_stats import (
    classify_trend, sen_intercept, TREND_LABELS,
    TREND_INCREASING, TREND_DECREASING, TREND_NONE,
)
from ..core.panel import read_panel
from .symbology import attach_categorized_symbology


class TemporalTrendAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    P_THRESHOLD = "P_THRESHOLD"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "temporal_trend"

    def displayName(self) -> str:
        return "Temporal Trend Analysis (Mann-Kendall + Theil-Sen)"

    def group(self) -> str:
        return "Spatiotemporal Analysis"

    def groupId(self) -> str:
        return "spatiotemporal_analysis"

    def createInstance(self):
        return TemporalTrendAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Detect monotonic trends per location with the non-parametric "
            "Mann-Kendall test and the robust Theil-Sen slope estimator.\n\n"
            "Each location is classified as Increasing, Decreasing, or No "
            "significant trend at the chosen significance level.\n\n"
            "Output fields: location_id, n_obs, mk_tau, mk_p_value, sen_slope, "
            "sen_intercept, trend_code (0/1/2), trend."
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
            self.P_THRESHOLD, "Significance threshold (p-value)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.05, minValue=0.001, maxValue=0.2))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Temporal trend output"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        p_threshold = self.parameterAsDouble(parameters, self.P_THRESHOLD, context)

        panel = read_panel(source, id_field, time_field, value_field)
        if panel.n_locations < 1:
            raise QgsProcessingException("No valid panel data found.")
        if panel.n_times < 3:
            raise QgsProcessingException(
                f"Need >= 3 time steps for a trend test (got {panel.n_times}).")

        feedback.pushInfo(
            f"Temporal trend: {panel.n_locations} locations x {panel.n_times} steps")

        out_fields = QgsFields()
        out_fields.append(QgsField("location_id", QVariant.String))
        out_fields.append(QgsField("n_obs", QVariant.Int))
        out_fields.append(QgsField("mk_tau", QVariant.Double))
        out_fields.append(QgsField("mk_p_value", QVariant.Double))
        out_fields.append(QgsField("sen_slope", QVariant.Double))
        out_fields.append(QgsField("sen_intercept", QVariant.Double))
        out_fields.append(QgsField("trend_code", QVariant.Int))
        out_fields.append(QgsField("trend", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs())

        total = panel.n_locations
        counts = {TREND_INCREASING: 0, TREND_DECREASING: 0, TREND_NONE: 0}
        for i, loc in enumerate(panel.locations):
            if feedback.isCanceled():
                break
            series = panel.raw_series(loc)
            tau, p_mk, slope = mann_kendall_test(series)
            code = classify_trend(p_mk, slope, p_threshold)
            counts[code] = counts.get(code, 0) + 1
            intercept = sen_intercept(series, slope)

            feat = QgsFeature(out_fields)
            feat.setGeometry(panel.loc_geom.get(loc, QgsGeometry()))
            feat.setAttributes([
                loc, len(series), round(tau, 6), round(p_mk, 6),
                round(slope, 6), round(intercept, 6), code, TREND_LABELS[code],
            ])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / total))

        feedback.pushInfo(
            f"Trends — increasing: {counts[TREND_INCREASING]}, "
            f"decreasing: {counts[TREND_DECREASING]}, "
            f"none: {counts[TREND_NONE]}")

        attach_categorized_symbology(
            context, dest_id, self.OUTPUT, "trend_code",
            [(TREND_INCREASING, "#d7301f", TREND_LABELS[TREND_INCREASING]),
             (TREND_DECREASING, "#2166ac", TREND_LABELS[TREND_DECREASING]),
             (TREND_NONE, "#e8e8e8", TREND_LABELS[TREND_NONE])],
            feedback)

        return {self.OUTPUT: dest_id}
