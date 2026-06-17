# -*- coding: utf-8 -*-
"""
Shared auto-symbology helpers for Processing outputs.

Builds a categorized renderer and a layer post-processor so analysis results
arrive on the map already styled.  A module-level keep-alive list holds the
post-processor instances — QGIS takes a borrowed pointer and the Python object
would otherwise be garbage-collected before the layer loads.
"""
from __future__ import annotations

from typing import List, Tuple

from qgis.core import QgsProcessingLayerPostProcessorInterface

# Holds post-processor instances alive past the algorithm's lifetime.
_KEEP_ALIVE: list = []


def build_categorized_renderer(field: str, entries: List[Tuple[object, str, str]], geometry_type):
    """
    entries: list of ``(value, color_hex, label)``.
    Returns a QgsCategorizedSymbolRenderer, or ``None`` on failure.
    """
    from qgis.PyQt.QtGui import QColor
    from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol

    categories = []
    for value, color_hex, label in entries:
        symbol = QgsSymbol.defaultSymbol(geometry_type)
        if symbol is None:
            continue
        symbol.setColor(QColor(color_hex))
        # Soft white hairline border for polygons keeps clusters legible.
        if geometry_type == 2:
            for idx in range(symbol.symbolLayerCount()):
                sl = symbol.symbolLayer(idx)
                if hasattr(sl, "setStrokeColor"):
                    sl.setStrokeColor(QColor(255, 255, 255, 140))
                if hasattr(sl, "setStrokeWidth"):
                    sl.setStrokeWidth(0.2)
        categories.append(QgsRendererCategory(str(value), symbol, label))
    if not categories:
        return None
    return QgsCategorizedSymbolRenderer(field, categories)


class CategorizedPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Apply a categorized renderer to the loaded output layer."""

    def __init__(self, field: str, entries: List[Tuple[object, str, str]]):
        super().__init__()
        self.field = field
        self.entries = entries

    def postProcessLayer(self, layer, context, feedback) -> None:
        if not layer:
            return
        try:
            renderer = build_categorized_renderer(self.field, self.entries, layer.geometryType())
            if renderer is not None:
                layer.setRenderer(renderer)
                layer.triggerRepaint()
        except Exception as exc:  # pragma: no cover - styling must never break a run
            try:
                feedback.pushWarning(f"Could not apply automatic symbology: {exc}")
            except Exception:
                pass


def attach_categorized_symbology(context, dest_id, output_key, field, entries, feedback=None) -> None:
    """
    Register a :class:`CategorizedPostProcessor` for the output layer if it
    will be loaded on completion.  Safe to call unconditionally.
    """
    try:
        pp = CategorizedPostProcessor(field, entries)
        if context.willLoadLayerOnCompletion(dest_id):
            context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(pp)
            _KEEP_ALIVE.append(pp)
        elif context.willLoadLayerOnCompletion(output_key):
            context.layerToLoadOnCompletionDetails(output_key).setPostProcessor(pp)
            _KEEP_ALIVE.append(pp)
    except Exception as exc:
        if feedback is not None:
            try:
                feedback.pushWarning(f"Could not register symbology: {exc}")
            except Exception:
                pass
