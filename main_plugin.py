# -*- coding: utf-8 -*-
"""PlanX DataCube Lab — Main plugin orchestrator."""
from __future__ import annotations

import os
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication

from .processing.datacube_provider import DataCubeProvider


class PlanXDataCube:
    """Top-level QGIS plugin: registers Processing provider and menu/dock."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.provider: DataCubeProvider | None = None
        self.menu: QMenu | None = None
        self.actions: list[QAction] = []
        self.dock = None

    def initGui(self) -> None:
        icon_path = os.path.join(self.plugin_dir, "icons", "icon.png")
        menu_icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        # processing provider
        self.provider = DataCubeProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        # menu
        self.menu = QMenu("DataCube", self.iface.mainWindow().menuBar())
        self.menu.menuAction().setIcon(menu_icon)

        parent_menu = None
        for action in self.iface.mainWindow().menuBar().actions():
            if action.text() == "PlanX":
                parent_menu = action.menu()
                break
        if parent_menu:
            parent_menu.addMenu(self.menu)
        else:
            self.iface.mainWindow().menuBar().addMenu(self.menu)

        self._add_action("datacube_dock", "DataCube Panel", self._toggle_dock, "cube_viz.png")

    def _add_action(self, key: str, label: str, callback, icon_name: str) -> None:
        icon_path = os.path.join(self.plugin_dir, "icons", icon_name)
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        action = QAction(icon, label, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.menu.addAction(action)
        self.actions.append(action)

    def _toggle_dock(self) -> None:
        if self.dock is None:
            from .ui.datacube_dock import DataCubeDock
            self.dock = DataCubeDock(self.iface)
            self.iface.addDockWidget(2, self.dock)
        self.dock.setVisible(not self.dock.isVisible())

    def unload(self) -> None:
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
        if self.menu:
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
        for action in self.actions:
            self.menu.removeAction(action)
        self.actions.clear()
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
