# -*- coding: utf-8 -*-
"""DataCube Dock — Minimalist panel for cube parameter management."""
from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDockWidget, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QGroupBox, QListWidget, QListWidgetItem, QCheckBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.core import QgsProject, QgsMapLayer, QgsRasterLayer


class DataCubeDock(QDockWidget):
    """Dockable panel for DataCube Lab operations."""

    def __init__(self, iface, parent=None):
        super().__init__("DataCube Lab", parent)
        self.iface = iface
        self.setObjectName("DataCubeDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(320)

        self.tabs = QTabWidget()
        self.setWidget(self.tabs)

        self._build_cube_tab()
        self._build_ehsa_tab()
        self._build_forecast_tab()

    def _make_group(self, title: str) -> QGroupBox:
        gb = QGroupBox(title)
        gb.setFont(QFont("Inter, Segoe UI", 9, QFont.Bold))
        gb.setStyleSheet(
            "QGroupBox { border: 1px solid #bbb; border-radius: 6px; margin-top: 8px; padding: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        return gb

    # -------------------------------------------------------------------
    # CUBE BUILDER TAB
    # -------------------------------------------------------------------
    def _build_cube_tab(self) -> None:
        w = QWidget()
        lyt = QVBoxLayout(w)

        gb = self._make_group("Build Data Cube")
        gl = QVBoxLayout(gb)

        gl.addWidget(QLabel("Select time-step layers (multi-select):"))
        self.cube_layer_list = QListWidget()
        self.cube_layer_list.setSelectionMode(QListWidget.ExtendedSelection)
        gl.addWidget(self.cube_layer_list)

        gl.addWidget(QLabel("Value field:"))
        self.cube_value_field = QComboBox()
        gl.addWidget(self.cube_value_field)

        gl.addWidget(QLabel("Grid resolution (map units):"))
        self.cube_grid_res = QDoubleSpinBox()
        self.cube_grid_res.setRange(0.01, 1000000.0)
        self.cube_grid_res.setValue(100.0)
        self.cube_grid_res.setDecimals(2)
        gl.addWidget(self.cube_grid_res)

        btn = QPushButton("Build Data Cube")
        btn.clicked.connect(self._on_build_cube)
        gl.addWidget(btn)
        lyt.addWidget(gb)
        lyt.addStretch()
        self.tabs.addTab(w, "Cube Builder")

        # populate
        self._populate_layer_list(self.cube_layer_list)

    # -------------------------------------------------------------------
    # EHSA TAB
    # -------------------------------------------------------------------
    def _build_ehsa_tab(self) -> None:
        w = QWidget()
        lyt = QVBoxLayout(w)

        gb = self._make_group("Emerging Hot Spot Analysis")
        gl = QVBoxLayout(gb)

        self.ehsa_layer_cb = QComboBox()
        gl.addWidget(QLabel("Panel data layer:"))
        gl.addWidget(self.ehsa_layer_cb)
        self._populate_layer_combo(self.ehsa_layer_cb)

        self.ehsa_id_field = QComboBox()
        gl.addWidget(QLabel("Location ID field:"))
        gl.addWidget(self.ehsa_id_field)

        self.ehsa_time_field = QComboBox()
        gl.addWidget(QLabel("Time step field:"))
        gl.addWidget(self.ehsa_time_field)

        self.ehsa_value_field = QComboBox()
        gl.addWidget(QLabel("Value field:"))
        gl.addWidget(self.ehsa_value_field)

        self.ehsa_p_value = QDoubleSpinBox()
        self.ehsa_p_value.setRange(0.001, 0.2)
        self.ehsa_p_value.setValue(0.05)
        self.ehsa_p_value.setDecimals(3)
        self.ehsa_p_value.setSingleStep(0.01)
        gl.addWidget(QLabel("Significance threshold (p):"))
        gl.addWidget(self.ehsa_p_value)

        btn = QPushButton("Run EHSA (17 Patterns)")
        btn.clicked.connect(self._on_run_ehsa)
        gl.addWidget(btn)
        lyt.addWidget(gb)
        lyt.addStretch()
        self.tabs.addTab(w, "EHSA")

    # -------------------------------------------------------------------
    # FORECAST TAB
    # -------------------------------------------------------------------
    def _build_forecast_tab(self) -> None:
        w = QWidget()
        lyt = QVBoxLayout(w)

        gb = self._make_group("Time-Series Forecast")
        gl = QVBoxLayout(gb)

        self.forecast_layer_cb = QComboBox()
        gl.addWidget(QLabel("Panel data layer:"))
        gl.addWidget(self.forecast_layer_cb)
        self._populate_layer_combo(self.forecast_layer_cb)

        self.forecast_id_field = QComboBox()
        gl.addWidget(QLabel("Location ID field:"))
        gl.addWidget(self.forecast_id_field)

        self.forecast_time_field = QComboBox()
        gl.addWidget(QLabel("Time step field:"))
        gl.addWidget(self.forecast_time_field)

        self.forecast_value_field = QComboBox()
        gl.addWidget(QLabel("Value field:"))
        gl.addWidget(self.forecast_value_field)

        self.forecast_steps = QSpinBox()
        self.forecast_steps.setRange(1, 50)
        self.forecast_steps.setValue(5)
        gl.addWidget(QLabel("Forecast steps ahead:"))
        gl.addWidget(self.forecast_steps)

        self.forecast_method = QComboBox()
        self.forecast_method.addItems(["Auto", "ARIMA", "Random Forest", "Exponential Smoothing"])
        gl.addWidget(QLabel("Method:"))
        gl.addWidget(self.forecast_method)

        btn = QPushButton("Run Forecast")
        btn.clicked.connect(self._on_run_forecast)
        gl.addWidget(btn)
        lyt.addWidget(gb)
        lyt.addStretch()
        self.tabs.addTab(w, "Forecast")

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------
    def _populate_layer_combo(self, combo: QComboBox) -> None:
        combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            combo.addItem(layer.name(), layer.id())

    def _populate_layer_list(self, lst: QListWidget) -> None:
        lst.clear()
        for layer in QgsProject.instance().mapLayers().values():
            lst.addItem(layer.name())

    # -------------------------------------------------------------------
    # Handlers
    # -------------------------------------------------------------------
    def _on_build_cube(self) -> None:
        from qgis import processing
        processing.execAlgorithmDialog("planx_datacube:create_data_cube", {})

    def _on_run_ehsa(self) -> None:
        from qgis import processing
        processing.execAlgorithmDialog("planx_datacube:emerging_hot_spot_analysis", {})

    def _on_run_forecast(self) -> None:
        from qgis import processing
        processing.execAlgorithmDialog("planx_datacube:time_series_forecast", {})
