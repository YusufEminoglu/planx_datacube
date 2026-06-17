# -*- coding: utf-8 -*-
"""Local Outlier Analysis — Anselin Local Moran's I (LISA) over a panel."""
from __future__ import annotations

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
)
from qgis.PyQt.QtCore import QVariant

from ..core.local_morans import local_morans_i, LISA_LABELS, LISA_NS
from ..core.spatial_weights import build_weights, neighbour_counts
from ..core.panel import read_panel, centroid_xy


class LocalMoransAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    TIME_AGG = "TIME_AGG"
    SPATIAL_REL = "SPATIAL_REL"
    DISTANCE = "DISTANCE"
    N_NEIGHBORS = "N_NEIGHBORS"
    PERMUTATIONS = "PERMUTATIONS"
    P_THRESHOLD = "P_THRESHOLD"
    OUTPUT = "OUTPUT"

    AGG_MODES = [
        ("Mean over time", "mean"),
        ("Last value", "last"),
        ("Sum over time", "sum"),
        ("Maximum over time", "max"),
    ]
    SPATIAL_MODES = [
        ("Fixed distance band", "distance_band"),
        ("K nearest neighbours", "knn"),
    ]

    def name(self) -> str:
        return "local_morans_i"

    def displayName(self) -> str:
        return "Local Outlier Analysis (Local Moran's I)"

    def group(self) -> str:
        return "Spatiotemporal Analysis"

    def groupId(self) -> str:
        return "spatiotemporal_analysis"

    def createInstance(self):
        return LocalMoransAlgorithm()

    def shortHelpString(self) -> str:
        return (
            "Anselin Local Moran's I (LISA): find statistically significant "
            "spatial clusters and outliers.\n\n"
            "The panel is first reduced to one value per location (mean, last, "
            "sum or max over time), then each location is classified as:\n"
            "  - High-High / Low-Low cluster (surrounded by similar values)\n"
            "  - High-Low / Low-High outlier (surrounded by dissimilar values)\n"
            "  - Not significant\n\n"
            "Significance is assessed with a deterministic conditional "
            "permutation test. Output: location_id, agg_value, local_i, z_score, "
            "spatial_lag, p_value, cluster_code (0-4), cluster."
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
        self.addParameter(QgsProcessingParameterEnum(
            self.TIME_AGG, "Temporal aggregation",
            options=[a[0] for a in self.AGG_MODES], defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.SPATIAL_REL, "Spatial relationship",
            options=[m[0] for m in self.SPATIAL_MODES], defaultValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, "Distance band (map units; 0 = auto)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.0, minValue=0.0, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.N_NEIGHBORS, "Number of neighbours (KNN)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=8, minValue=1, maxValue=100, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.PERMUTATIONS, "Permutations",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=999, minValue=0, maxValue=9999))
        self.addParameter(QgsProcessingParameterNumber(
            self.P_THRESHOLD, "Significance threshold (pseudo p-value)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.05, minValue=0.001, maxValue=0.2))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "LISA cluster/outlier output"))

    @staticmethod
    def _aggregate(values, mode):
        if not values:
            return 0.0
        if mode == "last":
            return values[-1]
        if mode == "sum":
            return sum(values)
        if mode == "max":
            return max(values)
        return sum(values) / len(values)  # mean

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        agg_mode = self.AGG_MODES[self.parameterAsEnum(parameters, self.TIME_AGG, context)][1]
        spatial_mode = self.SPATIAL_MODES[
            self.parameterAsEnum(parameters, self.SPATIAL_REL, context)][1]
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        n_neighbors = self.parameterAsInt(parameters, self.N_NEIGHBORS, context)
        permutations = self.parameterAsInt(parameters, self.PERMUTATIONS, context)
        p_threshold = self.parameterAsDouble(parameters, self.P_THRESHOLD, context)

        panel = read_panel(source, id_field, time_field, value_field)
        loc_sorted = panel.locations
        if len(loc_sorted) < 3:
            raise QgsProcessingException("Need >= 3 spatial units for Local Moran's I.")

        # Aggregate to one value per location and gather centroids.
        agg_values = []
        coords = []
        missing = 0
        for loc in loc_sorted:
            series = panel.raw_series(loc)
            agg_values.append(self._aggregate(series, agg_mode))
            xy = centroid_xy(panel.loc_geom.get(loc))
            if xy is None:
                missing += 1
                coords.append((0.0, 0.0))
            else:
                coords.append(xy)
        if missing:
            raise QgsProcessingException(
                f"{missing} location(s) lack geometry — Local Moran's I needs a "
                "centroid for every spatial unit.")

        adjacency = build_weights(
            coords, mode=spatial_mode, k=n_neighbors, distance=distance,
            include_self=False, row_standardize=True)
        counts = neighbour_counts(adjacency)
        isolated = sum(1 for c in counts if c == 0)
        if isolated:
            feedback.pushWarning(
                f"{isolated} location(s) have no neighbours and stay Not Significant. "
                "Increase the distance band or neighbour count.")
        avg_nb = sum(counts) / len(counts) if counts else 0.0
        feedback.pushInfo(
            f"Local Moran's I: {len(loc_sorted)} units, avg neighbours {avg_nb:.1f}, "
            f"{permutations} permutations")

        res = local_morans_i(agg_values, adjacency, permutations=permutations,
                             p_threshold=p_threshold)

        out_fields = QgsFields()
        out_fields.append(QgsField("location_id", QVariant.String))
        out_fields.append(QgsField("agg_value", QVariant.Double))
        out_fields.append(QgsField("local_i", QVariant.Double))
        out_fields.append(QgsField("z_score", QVariant.Double))
        out_fields.append(QgsField("spatial_lag", QVariant.Double))
        out_fields.append(QgsField("p_value", QVariant.Double))
        out_fields.append(QgsField("cluster_code", QVariant.Int))
        out_fields.append(QgsField("cluster", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, source.wkbType(), source.sourceCrs())

        sig = 0
        for i, loc in enumerate(loc_sorted):
            if feedback.isCanceled():
                break
            code = res["cluster"][i]
            if code != LISA_NS:
                sig += 1
            feat = QgsFeature(out_fields)
            feat.setGeometry(panel.loc_geom.get(loc, QgsGeometry()))
            feat.setAttributes([
                loc, round(agg_values[i], 6), round(res["I"][i], 6),
                round(res["z"][i], 6), round(res["lag"][i], 6),
                round(res["p"][i], 6), code, LISA_LABELS[code],
            ])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * i / len(loc_sorted)))

        feedback.pushInfo(f"Significant clusters/outliers: {sig}/{len(loc_sorted)}")

        from .symbology import attach_categorized_symbology
        attach_categorized_symbology(
            context, dest_id, self.OUTPUT, "cluster_code",
            [(1, "#d7191c", LISA_LABELS[1]),
             (2, "#2c7bb6", LISA_LABELS[2]),
             (3, "#abd9e9", LISA_LABELS[3]),
             (4, "#fdae61", LISA_LABELS[4]),
             (0, "#e8e8e8", LISA_LABELS[0])],
            feedback)

        return {self.OUTPUT: dest_id}
