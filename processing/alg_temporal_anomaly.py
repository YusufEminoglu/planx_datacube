# -*- coding: utf-8 -*-
"""Temporal Anomaly Detection — robust per-location outlier flagging."""
from __future__ import annotations

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
)
from qgis.PyQt.QtCore import QVariant

from ..core.timeseries_stats import detect_anomalies
from ..core.panel import read_panel
from .symbology import attach_categorized_symbology
from ._help_mixin import DataCubeHelpMixin


class TemporalAnomalyAlgorithm(DataCubeHelpMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    THRESHOLD = "THRESHOLD"
    METHOD = "METHOD"
    OUTPUT = "OUTPUT"

    METHODS = [
        ("Robust (median / MAD z-score)", True),
        ("Standard (mean / std z-score)", False),
    ]

    def name(self) -> str:
        return "temporal_anomaly"

    def displayName(self) -> str:
        return "Temporal Anomaly Detection"

    def group(self) -> str:
        return "Spatiotemporal Analysis"

    def groupId(self) -> str:
        return "spatiotemporal_analysis"

    def createInstance(self):
        return TemporalAnomalyAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Flag anomalous time steps per location using a robust modified "
            "z-score (median / MAD) — resistant to the very outliers it looks "
            "for — or the classic mean / standard-deviation z-score.\n\n"
            "A point is anomalous when |z| >= the threshold (default 3.0).\n\n"
            "Output fields: location_id, n_obs, n_anomalies, anomaly_rate, "
            "max_abs_z, last_z, last_anomaly (1/0), first_anom_time, "
            "last_anom_time."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, "Input panel data layer", [QgsProcessing.SourceType.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD, "Location ID field", parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterField(
            self.TIME_FIELD, "Time step field (numeric)", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterField(
            self.VALUE_FIELD, "Value field", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, "Detection method",
            options=[m[0] for m in self.METHODS], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, "Anomaly threshold (|z|)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=3.0, minValue=0.5, maxValue=10.0))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Anomaly output"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context)
        robust = self.METHODS[self.parameterAsEnum(parameters, self.METHOD, context)][1]

        panel = read_panel(source, id_field, time_field, value_field)
        if panel.n_locations < 1:
            raise QgsProcessingException("No valid panel data found.")
        if panel.n_times < 3:
            raise QgsProcessingException(
                f"Need >= 3 time steps to detect anomalies (got {panel.n_times}).")

        feedback.pushInfo(
            f"Anomaly detection ({'robust' if robust else 'standard'}, "
            f"|z|>={threshold}): {panel.n_locations} locations")

        out_fields = QgsFields()
        out_fields.append(QgsField("location_id", QVariant.String))
        out_fields.append(QgsField("n_obs", QVariant.Int))
        out_fields.append(QgsField("n_anomalies", QVariant.Int))
        out_fields.append(QgsField("anomaly_rate", QVariant.Double))
        out_fields.append(QgsField("max_abs_z", QVariant.Double))
        out_fields.append(QgsField("last_z", QVariant.Double))
        out_fields.append(QgsField("last_anomaly", QVariant.Int))
        out_fields.append(QgsField("first_anom_time", QVariant.Int))
        out_fields.append(QgsField("last_anom_time", QVariant.Int))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs())

        total = panel.n_locations
        total_anom = 0
        loc_with_anom = 0
        for i, loc in enumerate(panel.locations):
            if feedback.isCanceled():
                break
            obs_times = sorted(panel.loc_times.get(loc, {}).keys())
            series = [panel.loc_times[loc][t] for t in obs_times]
            res = detect_anomalies(series, threshold=threshold, robust=robust)
            total_anom += res["n_anomalies"]
            if res["n_anomalies"]:
                loc_with_anom += 1
            first_t = obs_times[res["first_index"]] if res["first_index"] >= 0 else None
            last_t = obs_times[res["last_index"]] if res["last_index"] >= 0 else None

            feat = QgsFeature(out_fields)
            feat.setGeometry(panel.loc_geom.get(loc, QgsGeometry()))
            feat.setAttributes([
                loc, len(series), res["n_anomalies"], round(res["anomaly_rate"], 6),
                round(res["max_abs_z"], 6), round(res["last_z"], 6),
                1 if res["last_is_anomaly"] else 0, first_t, last_t,
            ])
            sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
            feedback.setProgress(int(100 * i / total))

        feedback.pushInfo(
            f"Found {total_anom} anomalies across {loc_with_anom}/{total} locations.")

        attach_categorized_symbology(
            context, dest_id, self.OUTPUT, "last_anomaly",
            [(1, "#e31a1c", "Most recent step anomalous"),
             (0, "#dfe6e9", "Most recent step normal")],
            feedback)

        return {self.OUTPUT: dest_id}
