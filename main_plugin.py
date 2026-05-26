# -*- coding: utf-8 -*-
"""PlanX DataCube Lab — Main plugin (Processing provider + production dashboard)."""
from __future__ import annotations

import os

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .processing.datacube_provider import DataCubeProvider


IS_QGIS4 = int(getattr(Qgis, "QGIS_VERSION_INT", 0)) >= 40000


class PlanXDataCube:
    """Top-level QGIS plugin: toolbar icon + menu + Processing provider + dashboard."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action = None
        self.dialog = None

    def initProcessing(self) -> None:
        if self.provider is not None:
            return
        self.provider = DataCubeProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:
        self.initProcessing()
        if not self.iface:
            return
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "PlanX DataCube Lab", self.iface.mainWindow())
        self.action.triggered.connect(self.open_dashboard)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&PlanX DataCube Lab", self.action)

    def open_dashboard(self) -> None:
        if self.dialog is None:
            from .ui.datacube_dashboard import DataCubeDashboard
            self.dialog = DataCubeDashboard(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def unload(self) -> None:
        if self.iface and self.action:
            self.iface.removePluginMenu("&PlanX DataCube Lab", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
