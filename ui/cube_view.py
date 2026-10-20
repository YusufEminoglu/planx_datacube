# -*- coding: utf-8 -*-
"""
Cube Workbench — build, inspect and animate a space-time cube inside QGIS.

The Processing side of DataCube Lab produces long-format panels and netCDF
files.  This module turns either representation into a rectangular grid and
paints three coordinated views:

* a space-time heatmap (cells × time),
* an isometric 3-D voxel preview,
* a per-cell time-series sparkline.

It intentionally uses only Qt painting (no matplotlib/WebEngine), so it works
in every QGIS 3.34+ / 4.x runtime without extra dependencies.
"""
from __future__ import annotations

import math
from typing import List, Optional

from qgis.core import QgsMapLayer, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
    QPainterPath, QPen, QPolygonF,
)
from qgis.PyQt.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from ..core.cube_grid import CubeGrid
from ..core.panel import read_panel


# ---------------------------------------------------------------------------
# Painting helpers
# ---------------------------------------------------------------------------

_RAMP = (
    (0.00, "#0c2233"),
    (0.18, "#0e4f5c"),
    (0.42, "#1f9e89"),
    (0.68, "#f2c14e"),
    (1.00, "#e4572e"),
)


def _ramp_color(t: float, alpha: int = 255) -> QColor:
    """Interpolate the DataCube colour ramp."""
    t = max(0.0, min(1.0, float(t)))
    for i in range(1, len(_RAMP)):
        p0, c0 = _RAMP[i - 1]
        p1, c1 = _RAMP[i]
        if t <= p1:
            span = max(1e-9, p1 - p0)
            f = (t - p0) / span
            a = QColor(c0)
            b = QColor(c1)
            color = QColor(
                int(a.red() + (b.red() - a.red()) * f),
                int(a.green() + (b.green() - a.green()) * f),
                int(a.blue() + (b.blue() - a.blue()) * f),
            )
            color.setAlpha(alpha)
            return color
    color = QColor(_RAMP[-1][1])
    color.setAlpha(alpha)
    return color


def _fmt(value: float, compact: bool = True) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    value = float(value)
    if compact:
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if abs(value) >= 10_000:
            return f"{value / 1_000:.1f}k"
    if abs(value) >= 100:
        return f"{value:,.1f}"
    if abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.3g}"


def _mouse_pos(event):
    """Return an integer QPoint for Qt5 and Qt6 mouse events."""
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


# ---------------------------------------------------------------------------
# Space-time heatmap
# ---------------------------------------------------------------------------

class CubeHeatmapWidget(QWidget):
    """Cells × time heatmap with hover read-out and click selection."""

    cellSelected = pyqtSignal(int)
    pointHovered = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._display: Optional[CubeGrid] = None
        self._grid: Optional[CubeGrid] = None
        self._current = 0
        self._selected = 0
        self._hover = None

    def set_grid(self, display: CubeGrid, grid: Optional[CubeGrid] = None) -> None:
        self._display = display
        self._grid = grid or display
        self._current = min(self._current, max(0, self._grid.n_times - 1))
        self._selected = min(self._selected, max(0, self._grid.n_cells - 1))
        self.update()

    def set_current_time(self, index: int) -> None:
        self._current = max(0, min(index, max(0, (self._grid.n_times if self._grid else 1) - 1)))
        self.update()

    def set_selected_cell(self, index: int) -> None:
        self._selected = max(0, min(index, max(0, (self._grid.n_cells if self._grid else 1) - 1)))
        self.update()

    # -- coordinate mapping ---------------------------------------------
    def _map_cell(self, row: int) -> int:
        if self._display is not None and self._display.cell_blocks:
            block = self._display.cell_blocks[row]
            return block[0]
        return row

    def _display_row(self, cell: int) -> int:
        if self._display is None:
            return 0
        if self._display.cell_blocks:
            for row, (start, end) in enumerate(self._display.cell_blocks):
                if start <= cell < end:
                    return row
        return min(cell, self._display.n_cells - 1)

    def _map_time(self, col: int) -> int:
        if self._display is not None and self._display.time_blocks:
            return self._display.time_blocks[col][0]
        return col

    def _display_col(self, time_index: int) -> int:
        if self._display is None:
            return 0
        if self._display.time_blocks:
            for col, (start, end) in enumerate(self._display.time_blocks):
                if start <= time_index < end:
                    return col
        return min(time_index, self._display.n_times - 1)

    def _plot_rect(self) -> QRectF:
        return QRectF(62, 18, max(40, self.width() - 62 - 68),
                      max(40, self.height() - 18 - 38))

    # -- painting -------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#08131d"))
        if self._display is None or self._display.n_cells == 0:
            painter.setPen(QColor("#7f9aa8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Build or load a cube to inspect it.")
            return

        grid = self._display
        rect = self._plot_rect()
        n_cells = grid.n_cells
        n_times = grid.n_times
        cell_w = rect.width() / max(1, n_times)
        cell_h = rect.height() / max(1, n_cells)
        low, high = grid.value_range()

        # Cells
        for r in range(n_cells):
            for c in range(n_times):
                value = grid.values[r][c]
                if math.isfinite(value):
                    color = _ramp_color((value - low) / (high - low))
                else:
                    color = QColor("#102330")
                painter.fillRect(
                    QRectF(rect.left() + c * cell_w, rect.top() + r * cell_h,
                           max(1.0, cell_w), max(1.0, cell_h)), color)

        # Grid lines for small matrices
        if cell_h >= 7 and cell_w >= 7:
            painter.setPen(QPen(QColor(8, 19, 29, 120), 0.5))
            for r in range(1, n_cells):
                y = rect.top() + r * cell_h
                painter.drawLine(QPointF(rect.left(), y),
                                 QPointF(rect.right(), y))
            for c in range(1, n_times):
                x = rect.left() + c * cell_w
                painter.drawLine(QPointF(x, rect.top()),
                                 QPointF(x, rect.bottom()))

        # Current time column + selected cell row
        col = self._display_col(self._current)
        painter.fillRect(
            QRectF(rect.left() + col * cell_w, rect.top(),
                   max(1.5, cell_w), rect.height()),
            QColor(255, 255, 255, 30))
        row = self._display_row(self._selected)
        painter.setPen(QPen(QColor("#f6d27a"), 1.4))
        painter.drawRect(
            QRectF(rect.left(), rect.top() + row * cell_h,
                   rect.width(), max(2.0, cell_h)).adjusted(-1, -1, 1, 1))

        # Axes
        painter.setPen(QColor("#8fb0bd"))
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        label_step = max(1, int(math.ceil(n_times / 8)))
        for c in range(0, n_times, label_step):
            label = grid.time_labels[c]
            painter.drawText(
                QRectF(rect.left() + c * cell_w - 22,
                       rect.bottom() + 6, cell_w + 44, 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label)
        if n_cells <= 14:
            for r in range(n_cells):
                painter.drawText(
                    QRectF(2, rect.top() + r * cell_h - 6, 56,
                           max(12, cell_h)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    grid.cell_ids[r])
        else:
            painter.drawText(QRectF(2, rect.top(), 56, 16),
                             Qt.AlignmentFlag.AlignRight, "cells")
            painter.drawText(QRectF(2, rect.bottom() - 16, 56, 16),
                             Qt.AlignmentFlag.AlignRight, str(n_cells))

        # Colour bar
        self._draw_colorbar(painter, rect, low, high)

        # Hover read-out
        if self._hover is not None:
            hr, hc = self._hover
            if 0 <= hr < n_cells and 0 <= hc < n_times:
                value = grid.values[hr][hc]
                text = f"{grid.cell_ids[hr]}  ·  {grid.time_labels[hc]}  ·  {_fmt(value)}"
                self._draw_badge(painter, text)

    def _draw_colorbar(self, painter: QPainter, rect: QRectF,
                       low: float, high: float) -> None:
        bar = QRectF(rect.right() + 18, rect.top(), 10, rect.height())
        gradient = QLinearGradient(bar.topLeft(), bar.bottomLeft())
        for pos, color in _RAMP:
            gradient.setColorAt(1.0 - pos, QColor(color))
        painter.fillRect(bar, QBrush(gradient))
        painter.setPen(QColor("#5f7d8a"))
        painter.drawRect(bar)
        painter.setPen(QColor("#9ab6c2"))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRectF(bar.left() - 2, bar.bottom() + 4, 46, 12),
                         Qt.AlignmentFlag.AlignLeft, _fmt(low))
        painter.drawText(QRectF(bar.left() - 2, bar.top() - 14, 46, 12),
                         Qt.AlignmentFlag.AlignLeft, _fmt(high))

    def _draw_badge(self, painter: QPainter, text: str) -> None:
        metrics = QFontMetrics(painter.font())
        width = metrics.horizontalAdvance(text) + 18
        box = QRectF(12, self.height() - 28, min(width, self.width() - 24), 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(6, 20, 30, 220))
        painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor("#d9edf3"))
        painter.drawText(box.adjusted(9, 0, -9, 0),
                         Qt.AlignmentFlag.AlignVCenter, text)

    # -- interaction ----------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        if self._display is None:
            return
        pos = _mouse_pos(event)
        rect = self._plot_rect()
        if rect.contains(pos):
            col = int((pos.x() - rect.left()) / max(1e-9, rect.width())
                      * self._display.n_times)
            row = int((pos.y() - rect.top()) / max(1e-9, rect.height())
                      * self._display.n_cells)
            col = max(0, min(col, self._display.n_times - 1))
            row = max(0, min(row, self._display.n_cells - 1))
            if self._hover != (row, col):
                self._hover = (row, col)
                self.pointHovered.emit(self._map_cell(row),
                                       self._map_time(col))
                self.update()
        elif self._hover is not None:
            self._hover = None
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        if self._display is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = _mouse_pos(event)
        rect = self._plot_rect()
        if not rect.contains(pos):
            return
        row = int((pos.y() - rect.top()) / max(1e-9, rect.height())
                  * self._display.n_cells)
        row = max(0, min(row, self._display.n_cells - 1))
        cell = self._map_cell(row)
        self._selected = cell
        self.cellSelected.emit(cell)
        self.update()


# ---------------------------------------------------------------------------
# Isometric 3-D voxel preview
# ---------------------------------------------------------------------------

class CubeVoxelWidget(QWidget):
    """A dependency-free isometric preview of the cube's voxel stack."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._grid: Optional[CubeGrid] = None
        self._current = 0
        self._current_label = ""

    def set_grid(self, grid: CubeGrid) -> None:
        self._grid = grid.downsample(22, 14)
        self._current = min(self._current, max(0, self._grid.n_times - 1))
        self._current_label = (self._grid.time_labels[self._current]
                               if self._grid.time_labels else "")
        self.update()

    def set_current_time(self, index: int, label: str = "") -> None:
        if self._grid is None:
            return
        if label:
            self._current_label = label
        if self._grid.time_blocks:
            for col, (start, end) in enumerate(self._grid.time_blocks):
                if start <= index < end:
                    self._current = col
                    if not label and self._grid.time_labels:
                        self._current_label = self._grid.time_labels[col]
                    self.update()
                    return
        self._current = max(0, min(index, self._grid.n_times - 1))
        if not label and self._grid.time_labels:
            self._current_label = self._grid.time_labels[self._current]
        self.update()

    def _project(self, c: float, r: float, z: float, scale: float,
                 ox: float, oy: float, z_step: float) -> QPointF:
        cos30 = 0.8660254
        return QPointF(
            ox + (c - r) * cos30 * scale,
            oy + ((c + r) * 0.5 - z * z_step) * scale,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#08131d"))
        if self._grid is None or self._grid.n_cells == 0:
            painter.setPen(QColor("#7f9aa8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "3-D voxel preview appears here.")
            return

        grid = self._grid
        n_cells = grid.n_cells
        n_times = grid.n_times
        ncols = max(1, int(math.ceil(math.sqrt(n_cells))))
        nrows = max(1, int(math.ceil(n_cells / ncols)))
        z_step = 0.52
        margin = 22
        # Bounds of the isometric box
        xs, ys = [], []
        for c in (0, ncols):
            for r in (0, nrows):
                for z in (0, n_times):
                    p = self._project(c, r, z, 1.0, 0.0, 0.0, z_step)
                    xs.append(p.x())
                    ys.append(p.y())
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        scale = min((self.width() - 2 * margin) / max(1e-6, maxx - minx),
                    (self.height() - 2 * margin) / max(1e-6, maxy - miny))
        ox = margin - minx * scale + (self.width() - 2 * margin
                                      - (maxx - minx) * scale) / 2.0
        oy = margin - miny * scale + (self.height() - 2 * margin
                                      - (maxy - miny) * scale) / 2.0
        low, high = grid.value_range()
        span = max(1e-9, high - low)

        def point(c, r, z):
            return self._project(c, r, z, scale, ox, oy, z_step)

        # Draw the translucent time slices from bottom (oldest) to top.
        for t in range(n_times):
            is_current = (t == self._current)
            for idx in range(n_cells):
                c = idx % ncols
                r = idx // ncols
                if r >= nrows:
                    continue
                value = grid.values[idx][t]
                if not math.isfinite(value):
                    continue
                intensity = max(0.0, min(1.0, (value - low) / span))
                color = _ramp_color(intensity, 255 if is_current else 46)
                quad = QPolygonF([
                    point(c, r, t), point(c + 1, r, t),
                    point(c + 1, r + 1, t), point(c, r + 1, t),
                ])
                painter.setPen(QPen(color.darker(135),
                                    0.6 if not is_current else 0.8))
                painter.setBrush(color)
                painter.drawPolygon(quad)

                if is_current:
                    height = 0.15 + 0.75 * intensity
                    top = t + height
                    left_face = QPolygonF([
                        point(c, r, t), point(c, r + 1, t),
                        point(c, r + 1, top), point(c, r, top),
                    ])
                    right_face = QPolygonF([
                        point(c + 1, r, t), point(c + 1, r + 1, t),
                        point(c + 1, r + 1, top), point(c + 1, r, top),
                    ])
                    top_face = QPolygonF([
                        point(c, r, top), point(c + 1, r, top),
                        point(c + 1, r + 1, top), point(c, r + 1, top),
                    ])
                    painter.setBrush(color.darker(125))
                    painter.drawPolygon(left_face)
                    painter.setBrush(color.darker(160))
                    painter.drawPolygon(right_face)
                    painter.setBrush(color.lighter(118))
                    painter.drawPolygon(top_face)

        # Caption + guide
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#9ab6c2"))
        label = self._current_label or (
            grid.time_labels[self._current] if grid.time_labels else "")
        painter.drawText(
            QRectF(14, self.height() - 24, self.width() - 28, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"t = {label}  ·  isometric voxel stack")
        painter.setPen(QPen(QColor(120, 190, 205, 80), 1))
        painter.drawLine(QPointF(14, self.height() - 28),
                         QPointF(self.width() - 14, self.height() - 28))


# ---------------------------------------------------------------------------
# Per-cell sparkline
# ---------------------------------------------------------------------------

class CubeSeriesWidget(QWidget):
    """Small time-series chart for the selected cell."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._values: List[float] = []
        self._times: List[float] = []
        self._label = ""
        self._current = 0

    def set_series(self, values: List[float], times: List[float],
                   label: str = "") -> None:
        self._values = list(values)
        self._times = list(times)
        self._label = label
        self.update()

    def set_current_time(self, index: int) -> None:
        self._current = index
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#08131d"))
        if not self._values:
            painter.setPen(QColor("#7f9aa8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Select a cell in the heatmap to see its series.")
            return

        rect = QRectF(42, 14, max(20, self.width() - 58),
                      max(20, self.height() - 32))
        finite = [v for v in self._values if math.isfinite(v)]
        if not finite:
            painter.setPen(QColor("#7f9aa8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             f"{self._label}: no finite values")
            return
        low, high = min(finite), max(finite)
        if abs(high - low) < 1e-12:
            high = low + 1.0
        n = len(self._values)
        step = rect.width() / max(1, n - 1)

        def xy(i, value):
            return (rect.left() + i * step,
                    rect.bottom() - (value - low) / (high - low) * rect.height())

        # Mean line
        mean = sum(finite) / len(finite)
        painter.setPen(QPen(QColor(130, 190, 205, 90), 1,
                            Qt.PenStyle.DashLine))
        my = xy(0, mean)[1]
        painter.drawLine(QPointF(rect.left(), my), QPointF(rect.right(), my))

        # Area + line, split on missing values
        path = QPainterPath()
        segment: List[QPointF] = []
        segments: List[List[QPointF]] = []
        for i, value in enumerate(self._values):
            if math.isfinite(value):
                segment.append(QPointF(*xy(i, value)))
            elif segment:
                segments.append(segment)
                segment = []
        if segment:
            segments.append(segment)
        for seg in segments:
            if len(seg) < 2:
                continue
            path.moveTo(seg[0])
            for p in seg[1:]:
                path.lineTo(p)
        painter.setPen(QPen(QColor("#5ad2c0"), 2))
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawPath(path)

        # Fill under the first complete segment for a little depth.
        if segments and len(segments[0]) >= 2:
            fill = QPainterPath()
            fill.moveTo(segments[0][0].x(), rect.bottom())
            for p in segments[0]:
                fill.lineTo(p)
            fill.lineTo(segments[0][-1].x(), rect.bottom())
            fill.closeSubpath()
            painter.fillPath(fill, QColor(90, 210, 192, 28))

        # Current time marker
        if 0 <= self._current < n:
            x = rect.left() + self._current * step
            painter.setPen(QPen(QColor(246, 210, 122, 180), 1))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        # Axes labels
        painter.setPen(QColor("#8fb0bd"))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRectF(2, rect.top() - 6, 36, 12),
                         Qt.AlignmentFlag.AlignRight, _fmt(high))
        painter.drawText(QRectF(2, rect.bottom() - 6, 36, 12),
                         Qt.AlignmentFlag.AlignRight, _fmt(low))
        painter.drawText(QRectF(rect.left(), rect.bottom() + 2,
                                rect.width(), 14),
                         Qt.AlignmentFlag.AlignLeft, self._label)


# ---------------------------------------------------------------------------
# Workbench
# ---------------------------------------------------------------------------

class CubeWorkbench(QWidget):
    """Interactive build + inspect surface used by the dashboard."""

    cubeBuilt = pyqtSignal()

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.grid: Optional[CubeGrid] = None
        self.display: Optional[CubeGrid] = None
        self.layer = None
        self._timer = QTimer(self)
        self._timer.setInterval(750)
        self._timer.timeout.connect(self._advance_time)
        self._build_ui()
        self._apply_style()
        self.refresh_layers()

    # -- construction ---------------------------------------------------
    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QLabel { color: #17323a; }
            QFrame#wbPanel {
                background: #ffffff;
                border: 1px solid #d6e3e7;
                border-radius: 12px;
            }
            QFrame#kpiCard {
                background: #f7fbfc;
                border: 1px solid #d6e3e7;
                border-left: 3px solid #1f9e89;
                border-radius: 10px;
            }
            QFrame#viewerPanel {
                background: #0b1722;
                border: 1px solid #1d3a4a;
                border-radius: 12px;
            }
            QLabel#wbTitle {
                color: #103743;
                font-size: 17px;
                font-weight: 800;
            }
            QLabel#wbSub { color: #55747d; font-size: 11px; }
            QLabel#kpiTitle {
                color: #5b7a83;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#kpiValue {
                color: #0f3340;
                font-size: 19px;
                font-weight: 800;
            }
            QLabel#viewerTitle {
                color: #9fc1cc;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#timeLabel {
                color: #244b57;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#primary {
                background: #167d73;
                color: #ffffff;
                border: 1px solid #11655d;
                border-radius: 8px;
                padding: 7px 14px;
                font-weight: 700;
            }
            QPushButton#primary:hover { background: #1b9489; }
            QPushButton#ghost {
                background: #ffffff;
                color: #1d6f82;
                border: 1px solid #b9d0d7;
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 600;
            }
            QPushButton#ghost:hover { background: #eef8f9; }
            QPushButton#play {
                background: #102f3d;
                color: #b9f3e8;
                border: 1px solid #1e5364;
                border-radius: 8px;
                padding: 4px 12px;
                font-weight: 700;
            }
            QComboBox, QLineEdit, QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #c9d9de;
                border-radius: 7px;
                padding: 5px 7px;
                color: #17323a;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #d8e6e9;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
                background: #167d73;
            }
        """)

    def _kpi(self, title: str) -> tuple:
        card = QFrame()
        card.setObjectName("kpiCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(1)
        cap = QLabel(title.upper())
        cap.setObjectName("kpiTitle")
        value = QLabel("—")
        value.setObjectName("kpiValue")
        layout.addWidget(cap)
        layout.addWidget(value)
        return card, value

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Cube Workbench")
        title.setObjectName("wbTitle")
        sub = QLabel(
            "Turn an event layer into a fishnet × time cube, then inspect "
            "every cell and time slice without leaving QGIS.")
        sub.setObjectName("wbSub")
        sub.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(sub)
        head.addLayout(title_box, 1)
        self.status = QLabel("Ready")
        self.status.setObjectName("timeLabel")
        head.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(head)

        # -- controls ---------------------------------------------------
        panel = QFrame()
        panel.setObjectName("wbPanel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(10, 9, 10, 9)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)

        self.layer_combo = QComboBox()
        self.layer_combo.setMinimumWidth(240)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        grid.addWidget(QLabel("Event layer"), 0, 0)
        grid.addWidget(self.layer_combo, 0, 1, 1, 3)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("ghost")
        self.refresh_btn.clicked.connect(self.refresh_layers)
        grid.addWidget(self.refresh_btn, 0, 4)

        self.time_combo = QComboBox()
        grid.addWidget(QLabel("Time field"), 1, 0)
        grid.addWidget(self.time_combo, 1, 1, 1, 2)
        self.value_combo = QComboBox()
        grid.addWidget(QLabel("Value field"), 1, 3)
        grid.addWidget(self.value_combo, 1, 4)

        self.agg_combo = QComboBox()
        for label, _key in (
            ("Count", "count"), ("Sum", "sum"), ("Mean", "mean"),
            ("Maximum", "max"), ("Minimum", "min"),
        ):
            self.agg_combo.addItem(label, _key)
        grid.addWidget(QLabel("Aggregation"), 2, 0)
        grid.addWidget(self.agg_combo, 2, 1)

        self.grid_spin = QDoubleSpinBox()
        self.grid_spin.setRange(0.000001, 1_000_000_000.0)
        self.grid_spin.setDecimals(2)
        self.grid_spin.setValue(1000.0)
        self.grid_spin.setSuffix(" map units")
        self.grid_spin.setMinimumWidth(150)
        grid.addWidget(QLabel("Grid cell"), 2, 2)
        grid.addWidget(self.grid_spin, 2, 3)

        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.0, 1_000_000_000.0)
        self.step_spin.setDecimals(3)
        self.step_spin.setValue(0.0)
        self.step_spin.setSpecialValueText("one bin per value")
        grid.addWidget(QLabel("Time step"), 3, 0)
        grid.addWidget(self.step_spin, 3, 1)

        self.nc_edit = QLineEdit()
        self.nc_edit.setPlaceholderText("Optional netCDF path (.nc)")
        grid.addWidget(QLabel("netCDF"), 3, 2)
        grid.addWidget(self.nc_edit, 3, 3, 1, 2)
        nc_btn = QPushButton("…")
        nc_btn.setObjectName("ghost")
        nc_btn.setFixedWidth(30)
        nc_btn.clicked.connect(self._browse_nc_output)
        grid.addWidget(nc_btn, 3, 5)

        btn_row = QHBoxLayout()
        self.build_btn = QPushButton("Build Cube")
        self.build_btn.setObjectName("primary")
        self.build_btn.clicked.connect(self.build_cube)
        btn_row.addWidget(self.build_btn)
        self.open_btn = QPushButton("Load netCDF…")
        self.open_btn.setObjectName("ghost")
        self.open_btn.clicked.connect(self.load_netcdf)
        btn_row.addWidget(self.open_btn)
        self.map_btn = QPushButton("Zoom to Cube")
        self.map_btn.setObjectName("ghost")
        self.map_btn.clicked.connect(self.zoom_to_layer)
        btn_row.addWidget(self.map_btn)
        btn_row.addStretch()
        grid.addLayout(btn_row, 4, 0, 1, 6)
        root.addWidget(panel)

        # -- KPI row ----------------------------------------------------
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(6)
        self.kpi_cells, self._kpi_cells_value = self._kpi("Cells")
        self.kpi_times, self._kpi_times_value = self._kpi("Time steps")
        self.kpi_values, self._kpi_values_value = self._kpi("Observations")
        self.kpi_coverage, self._kpi_coverage_value = self._kpi("Coverage")
        self.kpi_range, self._kpi_range_value = self._kpi("Value range")
        for card in (self.kpi_cells, self.kpi_times, self.kpi_values,
                     self.kpi_coverage, self.kpi_range):
            kpi_row.addWidget(card, 1)
        root.addLayout(kpi_row)

        # -- viewers ----------------------------------------------------
        viewer_row = QHBoxLayout()
        viewer_row.setSpacing(7)

        heat_panel = QFrame()
        heat_panel.setObjectName("viewerPanel")
        heat_layout = QVBoxLayout(heat_panel)
        heat_layout.setContentsMargins(8, 7, 8, 8)
        heat_title = QLabel("SPACE–TIME HEATMAP")
        heat_title.setObjectName("viewerTitle")
        heat_layout.addWidget(heat_title)
        self.heatmap = CubeHeatmapWidget()
        self.heatmap.cellSelected.connect(self._on_cell_selected)
        self.heatmap.pointHovered.connect(self._on_hover)
        heat_layout.addWidget(self.heatmap, 1)
        viewer_row.addWidget(heat_panel, 3)

        voxel_panel = QFrame()
        voxel_panel.setObjectName("viewerPanel")
        voxel_layout = QVBoxLayout(voxel_panel)
        voxel_layout.setContentsMargins(8, 7, 8, 8)
        voxel_title = QLabel("3-D VOXEL PREVIEW")
        voxel_title.setObjectName("viewerTitle")
        voxel_layout.addWidget(voxel_title)
        self.voxel = CubeVoxelWidget()
        voxel_layout.addWidget(self.voxel, 1)

        time_head = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setObjectName("play")
        self.play_btn.setCheckable(True)
        self.play_btn.toggled.connect(self._toggle_play)
        time_head.addWidget(self.play_btn)
        self.time_label = QLabel("No cube loaded")
        self.time_label.setObjectName("timeLabel")
        time_head.addWidget(self.time_label, 1,
                            Qt.AlignmentFlag.AlignRight)
        voxel_layout.addLayout(time_head)
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 0)
        self.time_slider.valueChanged.connect(self._on_time_changed)
        voxel_layout.addWidget(self.time_slider)
        viewer_row.addWidget(voxel_panel, 2)
        root.addLayout(viewer_row, 1)

        # -- selected-cell series (full width) --------------------------
        series_panel = QFrame()
        series_panel.setObjectName("viewerPanel")
        series_layout = QVBoxLayout(series_panel)
        series_layout.setContentsMargins(8, 7, 8, 8)
        series_title = QLabel("SELECTED CELL SERIES")
        series_title.setObjectName("viewerTitle")
        series_layout.addWidget(series_title)
        self.series = CubeSeriesWidget()
        series_layout.addWidget(self.series, 1)
        root.addWidget(series_panel)

    # -- layer plumbing -------------------------------------------------
    def refresh_layers(self) -> None:
        current = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        panel_like = []
        other = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != QgsMapLayer.LayerType.VectorLayer:
                continue
            names = {f.name() for f in layer.fields()}
            if {"cell_id", "time_step", "value"} <= names:
                panel_like.append(layer)
            else:
                other.append(layer)
        for layer in panel_like + other:
            self.layer_combo.addItem(layer.name(), layer.id())
        if not panel_like and not other:
            self.layer_combo.addItem("No vector layers in project", "")
        if current:
            idx = self.layer_combo.findData(current)
            if idx >= 0:
                self.layer_combo.setCurrentIndex(idx)
        self.layer_combo.blockSignals(False)
        self._on_layer_changed()
        if panel_like and self.grid is None and self.layer is None:
            self.layer_combo.setCurrentIndex(0)
            self.load_panel_layer(panel_like[0])

    def _current_layer(self):
        layer_id = self.layer_combo.currentData()
        return QgsProject.instance().mapLayer(layer_id) if layer_id else None

    def _on_layer_changed(self) -> None:
        layer = self._current_layer()
        self.time_combo.clear()
        self.value_combo.clear()
        if layer is None:
            return
        names = [f.name() for f in layer.fields()]
        self.time_combo.addItems(names)
        self.value_combo.addItems(names)
        for combo, candidates in (
            (self.time_combo, ("time_step", "time", "year", "date")),
            (self.value_combo, ("value", "count", "population", "pop")),
        ):
            for candidate in candidates:
                idx = combo.findText(candidate)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    break
        if not self.time_combo.currentText() and names:
            self.time_combo.setCurrentIndex(0)
        if not self.value_combo.currentText() and names:
            self.value_combo.setCurrentIndex(min(1, len(names) - 1))

    def _browse_nc_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Write netCDF cube", "", "NetCDF (*.nc);;All files (*)")
        if path:
            self.nc_edit.setText(path)

    # -- build / load ---------------------------------------------------
    def build_cube(self) -> None:
        layer = self._current_layer()
        if layer is None:
            QMessageBox.warning(self, "Cube Workbench",
                                "Select a vector layer with a numeric time field.")
            return
        names = {f.name() for f in layer.fields()}
        if {"cell_id", "time_step", "value"} <= names:
            QMessageBox.warning(
                self, "Cube Workbench",
                "This layer is already a cube panel. Select the original event "
                "layer to build a new cube.")
            return
        time_field = self.time_combo.currentText()
        value_field = self.value_combo.currentText()
        if not time_field:
            QMessageBox.warning(self, "Cube Workbench", "Select a time field.")
            return
        agg_index = max(0, self.agg_combo.currentIndex())
        nc_path = self.nc_edit.text().strip() or None
        if nc_path and not nc_path.lower().endswith(".nc"):
            nc_path += ".nc"
            self.nc_edit.setText(nc_path)

        try:
            import processing
            from qgis.core import QgsProcessingFeedback
        except Exception as exc:
            QMessageBox.critical(self, "Cube Workbench",
                                 f"Processing is not available: {exc}")
            return

        self.status.setText("Building cube…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = processing.run(
                "planx_datacube:space_time_cube",
                {
                    "INPUT": layer,
                    "TIME_FIELD": time_field,
                    "VALUE_FIELD": value_field,
                    "AGG": agg_index,
                    "GRID_SIZE": float(self.grid_spin.value()),
                    "TIME_STEP": float(self.step_spin.value()),
                    "DROP_EMPTY": True,
                    "OUTPUT": "TEMPORARY_OUTPUT",
                    "OUTPUT_NC": nc_path,
                },
                feedback=QgsProcessingFeedback(),
            )
            out = result.get("OUTPUT") if isinstance(result, dict) else None
            if isinstance(out, str):
                out = QgsVectorLayer(out, "DataCube panel", "ogr")
            if out is None or not out.isValid():
                raise RuntimeError("The aggregation did not return a valid panel layer.")
            out.setName(f"DataCube · {layer.name()}")
            QgsProject.instance().addMapLayer(out)
            self.layer = out
            self.refresh_layers()
            self.load_panel_layer(out)
            note = f"  ·  netCDF: {nc_path}" if nc_path else ""
            self.status.setText(f"Built {out.featureCount():,} panel rows{note}")
            self.cubeBuilt.emit()
            if self.iface is not None:
                self.iface.messageBar().pushSuccess(
                    "DataCube Lab", f"Cube built: {out.featureCount()} panel rows.")
        except Exception as exc:
            self.status.setText("Build failed")
            QMessageBox.critical(self, "Cube Workbench", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def load_netcdf(self) -> None:
        from .voxel_config_dialog import NetCDFCubeDialog

        dlg = NetCDFCubeDialog(self)
        if not dlg.exec():
            return
        config = dlg.get_config()
        path = config["nc_path"]
        try:
            grid = CubeGrid.from_netcdf(path, config.get("variable", ""))
        except Exception as exc:
            QMessageBox.critical(self, "Cube Workbench",
                                 f"Could not read the netCDF cube:\n{exc}")
            return
        self.layer = None
        self.set_grid(grid)
        self.status.setText(f"Loaded {path}")
        self.cubeBuilt.emit()

    def load_panel_layer(self, layer) -> None:
        names = {f.name() for f in layer.fields()}
        id_field = "cell_id" if "cell_id" in names else (
            "location_id" if "location_id" in names else "")
        time_field = "time_step" if "time_step" in names else (
            "time" if "time" in names else "")
        value_field = "value" if "value" in names else ""
        if not id_field or not time_field or not value_field:
            QMessageBox.warning(
                self, "Cube Workbench",
                "The selected layer is not a long-format cube panel. "
                "Expected cell_id/location_id, time_step/time and value fields.")
            return
        panel = read_panel(layer, id_field, time_field, value_field)
        if panel.n_locations < 1 or panel.n_times < 1:
            QMessageBox.warning(self, "Cube Workbench",
                                "The panel has no valid cell/time observations.")
            return
        self.layer = layer
        self.set_grid(CubeGrid.from_panel(panel, source=layer.name()))
        self.status.setText(
            f"{layer.name()}  ·  {panel.n_locations:,} cells  ·  "
            f"{panel.n_times:,} time steps")

    def set_grid(self, grid: CubeGrid) -> None:
        self.grid = grid
        self.display = grid.downsample(72, 72)
        self.heatmap.set_grid(self.display, grid)
        self.voxel.set_grid(grid)
        self.time_slider.blockSignals(True)
        self.time_slider.setRange(0, max(0, grid.n_times - 1))
        self.time_slider.setValue(0)
        self.time_slider.blockSignals(False)
        self._update_kpis()
        self._select_first_cell()
        self._on_time_changed(0)

    def _update_kpis(self) -> None:
        if self.grid is None:
            for label in (self._kpi_cells_value, self._kpi_times_value,
                          self._kpi_values_value, self._kpi_coverage_value,
                          self._kpi_range_value):
                label.setText("—")
            return
        stats = self.grid.stats()
        self._kpi_cells_value.setText(f"{int(stats['n_cells']):,}")
        self._kpi_times_value.setText(f"{int(stats['n_times']):,}")
        self._kpi_values_value.setText(f"{int(stats['n_values']):,}")
        self._kpi_coverage_value.setText(f"{stats['coverage'] * 100:.0f}%")
        self._kpi_range_value.setText(
            f"{_fmt(stats['min'])} – {_fmt(stats['max'])}")

    def _select_first_cell(self) -> None:
        if self.grid is None:
            return
        for idx, row in enumerate(self.grid.values):
            if any(math.isfinite(v) for v in row):
                self.heatmap.set_selected_cell(idx)
                self._on_cell_selected(idx)
                return
        self._on_cell_selected(0)

    # -- interactions ---------------------------------------------------
    def _on_cell_selected(self, cell: int) -> None:
        if self.grid is None:
            return
        cell = max(0, min(cell, self.grid.n_cells - 1))
        self.heatmap.set_selected_cell(cell)
        self.series.set_series(
            self.grid.series(cell), self.grid.times,
            f"cell {self.grid.cell_ids[cell]}")
        self.series.set_current_time(self.time_slider.value())

    def _on_hover(self, cell: int, time_index: int) -> None:
        if self.grid is None:
            return
        if time_index < 0 or time_index >= self.grid.n_times:
            return
        value = self.grid.values[cell][time_index]
        self.status.setText(
            f"cell {self.grid.cell_ids[cell]}  ·  "
            f"{self.grid.time_labels[time_index]}  ·  {_fmt(value)}")

    def _on_time_changed(self, index: int) -> None:
        if self.grid is None:
            self.time_label.setText("No cube loaded")
            return
        index = max(0, min(index, self.grid.n_times - 1))
        self.heatmap.set_current_time(index)
        self.voxel.set_current_time(index, self.grid.time_labels[index])
        self.series.set_current_time(index)
        self.time_label.setText(
            f"t = {self.grid.time_labels[index]}   ({index + 1}/{self.grid.n_times})")

    def _toggle_play(self, active: bool) -> None:
        if active and self.grid is not None:
            self.play_btn.setText("❚❚ Pause")
            self._timer.start()
        else:
            self._timer.stop()
            self.play_btn.setText("▶ Play")

    def _advance_time(self) -> None:
        if self.grid is None:
            return
        nxt = self.time_slider.value() + 1
        if nxt >= self.grid.n_times:
            nxt = 0
        self.time_slider.setValue(nxt)

    def zoom_to_layer(self) -> None:
        if self.layer is None or self.iface is None:
            self.status.setText("No map layer to zoom to")
            return
        self.iface.setActiveLayer(self.layer)
        self.iface.zoomToActiveLayer()

    def sizeHint(self) -> QSize:
        return QSize(980, 720)
