# -*- coding: utf-8 -*-
"""QgsProcessingProvider for PlanX DataCube Lab."""
from __future__ import annotations

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .alg_create_cube import CreateDataCubeAlgorithm
from .alg_run_ehsa import RunEHSAAlgorithm
from .alg_forecast import ForecastAlgorithm
from .alg_space_time_cube import SpaceTimeCubeAlgorithm
from .alg_local_morans import LocalMoransAlgorithm
from .alg_temporal_trend import TemporalTrendAlgorithm
from .alg_temporal_anomaly import TemporalAnomalyAlgorithm
from .alg_forecast_backtest import ForecastBacktestAlgorithm


class DataCubeProvider(QgsProcessingProvider):
    PROVIDER_ID = "planx_datacube"
    PROVIDER_NAME = "PlanX DataCube Lab"

    def id(self) -> str:
        return self.PROVIDER_ID

    def name(self) -> str:
        return self.PROVIDER_NAME

    def longName(self) -> str:
        return "PlanX DataCube Lab — Spatiotemporal Analysis Engine"

    def icon(self) -> QIcon:
        base = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base, "icons", "icon.png")
        return QIcon(path) if os.path.exists(path) else super().icon()

    def loadAlgorithms(self) -> None:
        self.addAlgorithm(CreateDataCubeAlgorithm())
        self.addAlgorithm(SpaceTimeCubeAlgorithm())
        self.addAlgorithm(RunEHSAAlgorithm())
        self.addAlgorithm(LocalMoransAlgorithm())
        self.addAlgorithm(TemporalTrendAlgorithm())
        self.addAlgorithm(TemporalAnomalyAlgorithm())
        self.addAlgorithm(ForecastBacktestAlgorithm())
        self.addAlgorithm(ForecastAlgorithm())
