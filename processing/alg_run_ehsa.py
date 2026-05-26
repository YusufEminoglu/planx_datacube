# -*- coding: utf-8 -*-
"""Emerging Hot Spot Analysis — Processing algorithm."""
from __future__ import annotations

import math

from qgis.core import (
    QgsFeatureSink,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsProcessingOutputNumber,
    QgsWkbTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from ..core.statistics_ehsa import (
    getis_ord_g_star,
    mann_kendall_test,
    classify_ehsa_pattern,
    EHSA_LABELS,
)


class RunEHSAAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    ID_FIELD = "ID_FIELD"
    P_THRESHOLD = "P_THRESHOLD"
    N_CLASSES = "N_CLASSES"
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
            "Perform Emerging Hot Spot Analysis on panel data (vector layer with "
            "multiple time steps per spatial unit).\n\n"
            "For each spatial unit, the algorithm:\n"
            "  1. Computes Getis-Ord Gi* z-scores at each time step\n"
            "  2. Runs the Mann-Kendall trend test on the z-score series\n"
            "  3. Classifies the unit into one of 17 spatiotemporal patterns\n"
            "     (New, Consecutive, Intensifying, Persistent, Diminishing, "
            "Sporadic, Oscillating, Historical — Hot or Cold)\n\n"
            "Input must be a point or polygon layer with numeric time, unique ID, "
            "and value fields."
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
            QgsProcessingParameterField(self.TIME_FIELD, "Time step field (numeric: year, period index...)",
                                         parentLayerParameterName=self.INPUT,
                                         type=QgsProcessingParameterField.Numeric)
        )
        self.addParameter(
            QgsProcessingParameterField(self.VALUE_FIELD, "Value field",
                                         parentLayerParameterName=self.INPUT,
                                         type=QgsProcessingParameterField.Numeric)
        )
        self.addParameter(
            QgsProcessingParameterNumber(self.P_THRESHOLD, "Significance threshold (p-value)",
                                          type=QgsProcessingParameterNumber.Double,
                                          defaultValue=0.05, minValue=0.001, maxValue=0.2)
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, "EHSA classified output")
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        p_threshold = self.parameterAsDouble(parameters, self.P_THRESHOLD, context)

        # Organise data: {location_id: {time_step: value}}
        loc_times: dict = {}
        time_steps = set()
        location_ids = set()

        for feat in source.getFeatures():
            loc_id = feat[id_field]
            t = int(float(feat[time_field]))
            val = feat[value_field]
            if val is None or not math.isfinite(float(val)):
                continue
            location_ids.add(loc_id)
            time_steps.add(t)
            loc_times.setdefault(loc_id, {})[t] = float(val)

        time_sorted = sorted(time_steps)
        loc_sorted = sorted(location_ids)

        if len(time_sorted) < 3:
            raise QgsProcessingException(f"At least 3 time steps required (got {len(time_sorted)}).")
        if len(loc_sorted) < 2:
            raise QgsProcessingException("At least 2 spatial units required.")

        feedback.pushInfo(
            f"EHSA: {len(loc_sorted)} locations × {len(time_sorted)} time steps"
        )

        # Build z-score matrix: z_scores_by_time[t][loc]
        z_scores_by_time = []
        for t in time_sorted:
            values = [loc_times.get(loc, {}).get(t, 0.0) for loc in loc_sorted]
            z = getis_ord_g_star(values)
            z_scores_by_time.append(z)

        # Classify patterns
        patterns = classify_ehsa_pattern(z_scores_by_time, p_threshold)

        feedback.pushInfo(f"Classified {len(patterns)} locations into EHSA patterns.")

        # Also compute Mann-Kendall per location
        mk_results = {}
        for i, loc in enumerate(loc_sorted):
            series = [loc_times.get(loc, {}).get(t, 0.0) for t in time_sorted]
            tau, p_val, slope = mann_kendall_test(series)
            mk_results[loc] = (tau, p_val, slope)

        # Build output
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            source.fields(), source.wkbType(), source.sourceCrs(),
        )

        # collapse input to one row per location (use first geometry per location)
        loc_geom = {}
        for feat in source.getFeatures():
            g = feat.geometry()
            if g and not g.isEmpty():
                loc_geom.setdefault(feat[id_field], g)

        total = len(loc_sorted)
        for i, loc in enumerate(loc_sorted):
            if feedback.isCanceled():
                break
            pattern = patterns[i]
            tau, p_mk, slope = mk_results[loc]

            feat = QgsFeature()
            feat.setGeometry(loc_geom.get(loc, QgsGeometry()))
            feat.setAttributes([
                loc,                      # id
                pattern,                  # ehsa_code
                EHSA_LABELS[pattern],     # ehsa_label
                tau,                      # mk_tau
                p_mk,                     # mk_p_value
                slope,                    # mk_slope
            ])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / total))

        return {self.OUTPUT: dest_id}
