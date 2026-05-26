# -*- coding: utf-8 -*-
"""
Voxel Configuration Dialog — QGIS 4 Native Voxel Layer settings.

Provides a UI to expose parameters for rendering 4D data cubes as
volumetric voxel blocks in QGIS 4's 3D canvas.

Note: QGIS 4 native voxel support is evolving. This dialog serves
as a configuration bridge between the DataCube netCDF output and
the QGIS 4 voxel layer API.
"""
from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QDialogButtonBox, QFileDialog, QMessageBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsMapLayer


class VoxelConfigDialog(QDialog):
    """Dialog for configuring a 3D voxel layer from DataCube output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Voxel Layer")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        main_lyt = QVBoxLayout(self)

        # file selection
        file_lyt = QHBoxLayout()
        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setStyleSheet("color: #888; font-size: 11px;")
        btn_browse = QPushButton("Browse netCDF...")
        btn_browse.clicked.connect(self._browse_nc)
        file_lyt.addWidget(QLabel("netCDF file:"))
        file_lyt.addWidget(self.file_path_label, 1)
        file_lyt.addWidget(btn_browse)
        main_lyt.addLayout(file_lyt)

        # form
        form = QFormLayout()

        self.var_combo = QComboBox()
        form.addRow("Variable:", self.var_combo)

        self.z_scale = QDoubleSpinBox()
        self.z_scale.setRange(0.1, 100.0)
        self.z_scale.setValue(5.0)
        form.addRow("Z (time) exaggeration:", self.z_scale)

        self.voxel_size = QDoubleSpinBox()
        self.voxel_size.setRange(0.1, 10000.0)
        self.voxel_size.setValue(10.0)
        form.addRow("Voxel size (m):", self.voxel_size)

        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.0, 1.0)
        self.opacity.setValue(0.8)
        self.opacity.setSingleStep(0.05)
        form.addRow("Opacity:", self.opacity)

        self.smooth_cb = QCheckBox("Enable smooth shading")
        self.smooth_cb.setChecked(True)
        form.addRow("", self.smooth_cb)

        main_lyt.addLayout(form)

        # buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        main_lyt.addWidget(btn_box)

    def _browse_nc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select netCDF data cube", "", "NetCDF (*.nc);;All files (*)"
        )
        if path:
            self.file_path_label.setText(path)
            self.file_path_label.setStyleSheet("color: #333; font-size: 11px;")

    def _accept(self) -> None:
        nc_path = self.file_path_label.text()
        if nc_path == "No file selected" or not nc_path.endswith(".nc"):
            QMessageBox.warning(self, "Missing Input", "Select a valid netCDF (.nc) file.")
            return
        # The actual voxel layer creation is handled by the QGIS 4 API.
        # This dialog stores the configuration; the caller applies it.
        self.accept()

    def get_config(self) -> dict:
        """Return the configured parameters as a dictionary."""
        return {
            "nc_path": self.file_path_label.text(),
            "variable": self.var_combo.currentText(),
            "z_exaggeration": self.z_scale.value(),
            "voxel_size": self.voxel_size.value(),
            "opacity": self.opacity.value(),
            "smooth_shading": self.smooth_cb.isChecked(),
        }
