# -*- coding: utf-8 -*-
"""QGIS smoke test for PlanX DataCube Lab.

Run with the QGIS Python launcher from the plugins root::

    python-qgis -m planx_datacube.tests.smoke_plugin

The test loads the Processing provider, asserts that every advertised
algorithm is registered, and runs one real analysis on a tiny synthetic
panel.  It exits non-zero and prints FAIL when anything is missing.
"""
from __future__ import annotations

import os
import sys

os.environ.pop("QT_QPA_PLATFORM", None)

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

EXPECTED = [
    "create_data_cube",
    "space_time_cube",
    "emerging_hot_spot_analysis",
    "local_morans_i",
    "temporal_trend",
    "temporal_anomaly",
    "time_series_forecast",
    "forecast_backtest",
]


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    try:
        plugin_path = os.path.join(QgsApplication.prefixPath(), "python", "plugins")
        if os.path.isdir(plugin_path):
            sys.path.insert(0, plugin_path)
        import processing  # noqa: F401
        from processing.core.Processing import Processing

        Processing.initialize()
        from planx_datacube.processing.datacube_provider import DataCubeProvider

        provider = DataCubeProvider()
        # In a headless QGIS the registry does not always trigger a lazy
        # provider load, so load the algorithm list explicitly before adding.
        provider.load()
        if QgsApplication.processingRegistry().addProvider(provider):
            print("provider registered")
        provider.load()

        registry = QgsApplication.processingRegistry()
        missing = []
        for name in EXPECTED:
            alg = registry.algorithmById(f"planx_datacube:{name}")
            # Touching name() forces the lazy provider proxy to resolve; a
            # bare algorithmById() can return a placeholder in headless QGIS.
            if alg is None or not alg.name():
                missing.append(name)
        if missing:
            print("FAIL missing algorithms: " + ", ".join(missing))
            return 1
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3857&field=cell_id:integer"
            "&field=time_step:integer&field=value:double",
            "smoke_panel",
            "memory",
        )
        layer_provider = layer.dataProvider()
        features = []
        for cell in range(4):
            for step in range(3):
                feat = QgsFeature(layer.fields())
                feat.setGeometry(QgsGeometry.fromPointXY(
                    QgsPointXY(cell * 10.0, 0.0)))
                feat.setAttributes([cell, step, 1.0 + cell + step])
                features.append(feat)
        layer_provider.addFeatures(features)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)

        result = processing.run(
            "planx_datacube:emerging_hot_spot_analysis",
            {
                "INPUT": layer,
                "ID_FIELD": "cell_id",
                "TIME_FIELD": "time_step",
                "VALUE_FIELD": "value",
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )
        output = result.get("OUTPUT")
        if output is None or not output.isValid():
            print("FAIL EHSA did not produce a valid layer")
            return 1
        if output.featureCount() != 4:
            print(f"FAIL EHSA produced {output.featureCount()} rows, expected 4")
            return 1

        print(f"PASS 8 algorithms registered; EHSA produced {output.featureCount()} rows")
        return 0
    finally:
        app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
