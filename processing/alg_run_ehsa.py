# -*- coding: utf-8 -*-
"""Emerging Hot Spot Analysis — Processing algorithm."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QVariant

from ..core.statistics_ehsa import (
    getis_ord_g_star, mann_kendall_test, classify_ehsa_pattern, EHSA_LABELS,
)


class RunEHSAAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    P_THRESHOLD = "P_THRESHOLD"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "emerging_hot_spot_analysis"

    def displayName(self) -> str:
        return "Emerging Hot Spot Analysis (EHSA)"

    def group(self) -> str:
        return "Spatiotemporal Analysis"

    def groupId(self) -> str:
        return "spatiotemporal_analysis"

    def createInstance(self):
        return RunEHSAAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Perform Emerging Hot Spot Analysis on panel data.\n\n"
            "Classifies each spatial unit into one of 17 patterns using "
            "Getis-Ord Gi* z-scores and Mann-Kendall trend test.\n"
            "Output: one row per location with ehsa_code (0-16), "
            "ehsa_label, mk_tau, mk_p_value, mk_slope."
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
            self.OUTPUT, "EHSA classified output"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        p_threshold = self.parameterAsDouble(parameters, self.P_THRESHOLD, context)

        # Organise: {location_id: {time_step: value}}
        loc_times: dict = {}
        time_steps: set = set()
        location_ids: set = set()

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
            location_ids.add(loc_id)
            time_steps.add(t)
            loc_times.setdefault(loc_id, {})[t] = v

        time_sorted = sorted(time_steps)
        loc_sorted = sorted(location_ids)

        if len(time_sorted) < 3:
            raise QgsProcessingException(f"Need >= 3 time steps (got {len(time_sorted)}).")
        if len(loc_sorted) < 2:
            raise QgsProcessingException("Need >= 2 spatial units.")

        feedback.pushInfo(f"EHSA: {len(loc_sorted)} locations x {len(time_sorted)} steps")

        # Getis-Ord Gi* per time step
        z_by_t = []
        for t in time_sorted:
            vals = [loc_times.get(loc, {}).get(t, 0.0) for loc in loc_sorted]
            z_by_t.append(getis_ord_g_star(vals))

        # Classify
        patterns = classify_ehsa_pattern(z_by_t, p_threshold)

        # Mann-Kendall per location
        mk_results = {}
        for i, loc in enumerate(loc_sorted):
            series = [loc_times.get(loc, {}).get(t, 0.0) for t in time_sorted]
            mk_results[loc] = mann_kendall_test(series)

        # Collect geometry per location
        loc_geom = {}
        for feat in source.getFeatures():
            loc_id = str(feat[id_field])
            if loc_id not in loc_geom:
                g = feat.geometry()
                if g and not g.isEmpty():
                    loc_geom[loc_id] = g

        # Build output schema
        out_fields = QgsFields()
        out_fields.append(QgsField("location_id", QVariant.String))
        out_fields.append(QgsField("ehsa_code", QVariant.Int))
        out_fields.append(QgsField("ehsa_label", QVariant.String))
        out_fields.append(QgsField("mk_tau", QVariant.Double))
        out_fields.append(QgsField("mk_p_value", QVariant.Double))
        out_fields.append(QgsField("mk_slope", QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs(),
        )

        total = len(loc_sorted)
        for i, loc in enumerate(loc_sorted):
            if feedback.isCanceled():
                break
            pattern = patterns[i]
            tau, p_mk, slope = mk_results[loc]

            feat = QgsFeature(out_fields)
            feat.setGeometry(loc_geom.get(loc, QgsGeometry()))
            feat.setAttributes([
                loc,
                pattern,
                EHSA_LABELS.get(pattern, "Unknown"),
                round(tau, 6),
                round(p_mk, 6),
                round(slope, 6),
            ])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / total))

        feedback.pushInfo(f"EHSA complete: {total} locations classified.")
        return {self.OUTPUT: dest_id}
