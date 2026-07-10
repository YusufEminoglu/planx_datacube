# -*- coding: utf-8 -*-
"""Emerging Hot Spot Analysis — Processing algorithm."""
from __future__ import annotations

from qgis.core import (
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingLayerPostProcessorInterface,
)
from qgis.PyQt.QtCore import QVariant

from ..core.statistics_ehsa import (
    getis_ord_g_star, getis_ord_gi_star_matrix, mann_kendall_test,
    classify_ehsa_pattern, EHSA_LABELS,
)
from ..core.spatial_weights import build_weights, neighbour_counts
from ..core.panel import read_panel, centroid_xy
from ._help_mixin import DataCubeHelpMixin


class EHSASymbologyPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Post-processor to automatically apply standard 17-class symbology to EHSA output."""

    def postProcessLayer(self, layer, context, feedback) -> None:
        if not layer:
            return

        from qgis.PyQt.QtGui import QColor
        from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol
        from ..core.statistics_ehsa import EHSA_LABELS

        EHSA_COLORS = {
            0: "#e8e8e8",  # Not Significant
            1: "#ffcccc",  # New Hot Spot
            2: "#ff9999",  # Consecutive Hot Spot
            3: "#ff3333",  # Intensifying Hot Spot
            4: "#cc0000",  # Persistent Hot Spot
            5: "#ff6666",  # Diminishing Hot Spot
            6: "#ffb2b2",  # Sporadic Hot Spot
            7: "#ff80df",  # Oscillating Hot Spot
            8: "#d966ff",  # Historical Hot Spot
            9: "#cce6ff",  # New Cold Spot
            10: "#99ccff",  # Consecutive Cold Spot
            11: "#3399ff",  # Intensifying Cold Spot
            12: "#0066cc",  # Persistent Cold Spot
            13: "#66b2ff",  # Diminishing Cold Spot
            14: "#b2d8ff",  # Sporadic Cold Spot
            15: "#33cccc",  # Oscillating Cold Spot
            16: "#99e6e6",  # Historical Cold Spot
        }

        categories = []
        for code, label in EHSA_LABELS.items():
            color_hex = EHSA_COLORS.get(code, "#e8e8e8")
            color = QColor(color_hex)

            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            if symbol:
                symbol.setColor(color)
                # Clean semi-transparent borders for polygons
                if layer.geometryType() == 2:
                    for idx in range(symbol.symbolLayerCount()):
                        sl = symbol.symbolLayer(idx)
                        if hasattr(sl, 'setStrokeColor'):
                            sl.setStrokeColor(QColor(255, 255, 255, 140))
                        if hasattr(sl, 'setStrokeWidth'):
                            sl.setStrokeWidth(0.2)

                cat = QgsRendererCategory(str(code), symbol, label)
                categories.append(cat)

        renderer = QgsCategorizedSymbolRenderer("ehsa_code", categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()


class RunEHSAAlgorithm(DataCubeHelpMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ID_FIELD = "ID_FIELD"
    TIME_FIELD = "TIME_FIELD"
    VALUE_FIELD = "VALUE_FIELD"
    P_THRESHOLD = "P_THRESHOLD"
    SPATIAL_REL = "SPATIAL_REL"
    DISTANCE = "DISTANCE"
    N_NEIGHBORS = "N_NEIGHBORS"
    OUTPUT = "OUTPUT"

    SPATIAL_MODES = [
        ("No spatial weighting (global z-score)", "none"),
        ("Fixed distance band", "distance_band"),
        ("K nearest neighbours", "knn"),
    ]

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
            "Getis-Ord Gi* z-scores and the Mann-Kendall trend test.\n\n"
            "Spatial relationship: choose how neighbours are defined for the "
            "Gi* statistic. 'Fixed distance band' and 'K nearest neighbours' "
            "compute a true local hot/cold statistic from each location's "
            "neighbourhood (recommended); 'No spatial weighting' falls back to "
            "a global standardised z-score (useful when locations are not "
            "spatially comparable).\n\n"
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
        self.addParameter(QgsProcessingParameterEnum(
            self.SPATIAL_REL, "Spatial relationship (Gi* neighbourhood)",
            options=[m[0] for m in self.SPATIAL_MODES], defaultValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, "Distance band (map units; 0 = auto)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.0, minValue=0.0, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.N_NEIGHBORS, "Number of neighbours (KNN)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=8, minValue=1, maxValue=100, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "EHSA classified output"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        time_field = self.parameterAsString(parameters, self.TIME_FIELD, context)
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        p_threshold = self.parameterAsDouble(parameters, self.P_THRESHOLD, context)
        spatial_mode = self.SPATIAL_MODES[
            self.parameterAsEnum(parameters, self.SPATIAL_REL, context)][1]
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        n_neighbors = self.parameterAsInt(parameters, self.N_NEIGHBORS, context)

        panel = read_panel(source, id_field, time_field, value_field)
        loc_sorted = panel.locations
        time_sorted = panel.times
        loc_geom = panel.loc_geom

        if len(time_sorted) < 3:
            raise QgsProcessingException(f"Need >= 3 time steps (got {len(time_sorted)}).")
        if len(loc_sorted) < 2:
            raise QgsProcessingException("Need >= 2 spatial units.")

        feedback.pushInfo(f"EHSA: {len(loc_sorted)} locations x {len(time_sorted)} steps")

        # Build spatial weights from per-location centroids (Gi* includes self).
        adjacency = None
        if spatial_mode != "none":
            coords = []
            missing = 0
            for loc in loc_sorted:
                xy = centroid_xy(loc_geom.get(loc))
                if xy is None:
                    missing += 1
                    coords.append((0.0, 0.0))
                else:
                    coords.append(xy)
            if missing:
                feedback.pushWarning(
                    f"{missing} location(s) lack geometry; falling back to a "
                    "global z-score (no spatial weighting).")
                spatial_mode = "none"
            else:
                adjacency = build_weights(
                    coords, mode=spatial_mode, k=n_neighbors,
                    distance=distance, include_self=True, row_standardize=False)
                counts = neighbour_counts(adjacency)  # includes the self term
                avg_nb = (sum(counts) / len(counts) - 1.0) if counts else 0.0
                if spatial_mode == "distance_band":
                    band_str = "auto" if distance <= 0 else f"{distance:.4g}"
                    feedback.pushInfo(
                        f"Gi* spatial weights: fixed distance band ({band_str}); "
                        f"avg neighbours/location: {avg_nb:.1f}")
                else:
                    feedback.pushInfo(
                        f"Gi* spatial weights: {n_neighbors} nearest neighbours; "
                        f"avg neighbours/location: {avg_nb:.1f}")

        # Getis-Ord Gi* per time step (weighted if a neighbourhood is defined).
        z_by_t = []
        for t in time_sorted:
            vals = [panel.loc_times.get(loc, {}).get(t, 0.0) for loc in loc_sorted]
            if adjacency is not None:
                z_by_t.append(getis_ord_gi_star_matrix(vals, adjacency))
            else:
                z_by_t.append(getis_ord_g_star(vals))

        # Classify
        patterns = classify_ehsa_pattern(z_by_t, p_threshold)

        # Mann-Kendall per location
        mk_results = {}
        for i, loc in enumerate(loc_sorted):
            series = [panel.loc_times.get(loc, {}).get(t, 0.0) for t in time_sorted]
            mk_results[loc] = mann_kendall_test(series)

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

        # Register post-processor for automatic layer styling
        try:
            if context.willLoadLayerOnCompletion(dest_id):
                layer_details = context.layerToLoadOnCompletionDetails(dest_id)
                layer_details.setPostProcessor(EHSASymbologyPostProcessor())
            elif context.willLoadLayerOnCompletion(self.OUTPUT):
                layer_details = context.layerToLoadOnCompletionDetails(self.OUTPUT)
                layer_details.setPostProcessor(EHSASymbologyPostProcessor())
        except Exception as exc:
            feedback.pushWarning(f"Could not apply automatic EHSA symbology: {exc}")

        feedback.pushInfo(f"EHSA complete: {total} locations classified.")
        return {self.OUTPUT: dest_id}
