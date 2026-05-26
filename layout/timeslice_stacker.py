# -*- coding: utf-8 -*-
"""
Time-Slice Layout Stacker — Stack temporal layers in a print layout.

Creates a QGIS Print Layout where each time step appears as a separate
map item stacked vertically or diagonally, showing the progression of
a spatial variable through time.
"""
from __future__ import annotations

from typing import List

from qgis.PyQt.QtGui import QFont, QColor
from qgis.core import (
    QgsLayout, QgsLayoutItemMap, QgsLayoutItemLabel,
    QgsLayoutPoint, QgsLayoutSize, QgsProject, QgsRectangle,
    QgsUnitTypes, QgsMapLayer,
)


def create_time_slice_layout(
    layers_by_time: List[QgsMapLayer],
    layout_name: str = "Time_Slices",
    page_width_mm: float = 420.0,
    page_height_mm: float = 297.0,
    stack_direction: str = "vertical",
    spacing_mm: float = 8.0,
    map_scale: float = 100000.0,
    label_time_steps: List[str] | None = None,
) -> QgsLayout:
    """
    Create a layout stacking temporal layers vertically or diagonally.

    Parameters
    ----------
    layers_by_time : list[QgsMapLayer]
        Layers in temporal order (oldest first).
    layout_name : str
        Name for the layout in the layout manager.
    page_width_mm, page_height_mm : float
        Page dimensions in millimetres.
    stack_direction : str
        "vertical" or "diagonal".
    spacing_mm : float
        Gap between stacked map items.
    map_scale : float
        Scale denominator for each map item.
    label_time_steps : list[str] | None
        Labels for each time step (e.g. ["2020", "2021", ...]).
        If None, uses layer names.

    Returns
    -------
    QgsLayout — added to the project layout manager.
    """
    n = len(layers_by_time)
    if n < 2:
        raise ValueError("Need at least 2 time-step layers.")

    project = QgsProject.instance()
    layout = QgsLayout(project)
    layout.initializeDefaults()
    layout.setName(layout_name)

    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(page_width_mm, page_height_mm,
                                    QgsUnitTypes.LayoutMillimeters))

    # compute a common extent
    extent = QgsRectangle(layers_by_time[0].extent())
    for layer in layers_by_time[1:]:
        extent.combineExtentWith(layer.extent())
    extent.scale(1.1)

    # determine map size based on n and spacing
    if stack_direction == "vertical":
        map_h = (page_height_mm - (n + 1) * spacing_mm) / n
        map_w = page_width_mm - 2 * spacing_mm
    else:  # diagonal
        map_h = (page_height_mm - (n + 1) * spacing_mm) / n
        map_w = (page_width_mm - (n + 1) * spacing_mm) / n

    labels = label_time_steps if label_time_steps else [lyr.name() for lyr in layers_by_time]

    for i, (layer, lbl) in enumerate(zip(layers_by_time, labels)):
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(0, 0, map_w, map_h)
        map_item.setExtent(extent)
        map_item.setScale(map_scale)
        map_item.setLayers([layer])
        map_item.setKeepLayerSet(True)

        if stack_direction == "vertical":
            x = spacing_mm
            y = spacing_mm + i * (map_h + spacing_mm)
        else:
            x = spacing_mm + i * (map_w * 0.3)
            y = page_height_mm - map_h - spacing_mm - i * (map_h * 0.3)

        map_item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))

        # time-step label
        label_item = QgsLayoutItemLabel(layout)
        label_item.setText(lbl)
        font = QFont("Inter, Segoe UI", 10)
        font.setBold(True)
        label_item.setFont(font)
        label_item.adjustSizeToText()
        label_item.attemptMove(
            QgsLayoutPoint(x, y - 7, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addLayoutItem(label_item)
        layout.addLayoutItem(map_item)

    # add title
    title = QgsLayoutItemLabel(layout)
    title.setText("Spatiotemporal Progression")
    title_font = QFont("Inter, Segoe UI", 14)
    title_font.setBold(True)
    title.setFont(title_font)
    title.adjustSizeToText()
    title.attemptMove(QgsLayoutPoint(
        page_width_mm / 2 - 60, 2, QgsUnitTypes.LayoutMillimeters
    ))
    layout.addLayoutItem(title)

    project.layoutManager().addLayout(layout)
    return layout
