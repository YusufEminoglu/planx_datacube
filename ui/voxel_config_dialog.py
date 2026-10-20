# -*- coding: utf-8 -*-
"""
netCDF cube picker for the DataCube Workbench.

Loads the variable list from a CF-style netCDF file produced by the
Space-Time Cube or Cube Builder algorithms.  The selected file and variable
are rendered by the integrated 3D voxel preview — no native QGIS voxel layer
API is required (QGIS 3.44 and 4.2 do not expose one).
"""
from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)


class NetCDFCubeDialog(QDialog):
    """Dialog for choosing a netCDF cube and one of its data variables."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open netCDF Cube")
        self.setMinimumWidth(460)
        self._path = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setStyleSheet("color:#6a858d; font-size:11px;")
        browse = QPushButton("Browse netCDF…")
        browse.clicked.connect(self._browse_nc)
        file_row.addWidget(QLabel("netCDF file"))
        file_row.addWidget(self.file_path_label, 1)
        file_row.addWidget(browse)
        layout.addLayout(file_row)

        form = QFormLayout()
        self.var_combo = QComboBox()
        self.var_combo.setMinimumWidth(220)
        form.addRow("Data variable", self.var_combo)
        layout.addLayout(form)

        hint = QLabel(
            "The cube is displayed in the Workbench heatmap, 3-D voxel preview "
            "and per-cell series. Expected dimensions: time × y × x.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6a858d; font-size:11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_nc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select netCDF data cube", "",
            "NetCDF (*.nc *.nc4);;All files (*)")
        if not path:
            return
        self._path = path
        self.file_path_label.setText(path)
        self.file_path_label.setStyleSheet("color:#17323a; font-size:11px;")
        self.var_combo.clear()
        try:
            import netCDF4
            with netCDF4.Dataset(path, "r") as ds:
                variables = [
                    name for name, var in ds.variables.items()
                    if var.ndim == 3
                    and name not in ("x", "y", "time", "crs", "x_bnds", "y_bnds")
                ]
                if not variables:
                    variables = ["value"]
                self.var_combo.addItems(variables)
        except Exception:
            self.var_combo.addItem("value")

    def _accept(self) -> None:
        path = self._path or self.file_path_label.text()
        if not path or path == "No file selected" or not path.lower().endswith((".nc", ".nc4")):
            QMessageBox.warning(self, "Open netCDF Cube",
                                "Select a valid netCDF (.nc) file.")
            return
        self.accept()

    def get_config(self) -> dict:
        """Return the selected file and data variable."""
        return {
            "nc_path": self._path or self.file_path_label.text(),
            "variable": self.var_combo.currentText(),
        }
