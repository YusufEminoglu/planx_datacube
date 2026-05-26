# -*- coding: utf-8 -*-
"""
PlanX DataCube Lab — Next-generation spatiotemporal analysis engine.
Multi-dimensional (X×Y×T×V) data cube construction, Emerging Hot Spot
Analysis, time-series forecasting, and volumetric voxel rendering for QGIS.

classFactory returns the PlanXDataCube instance.
"""


def classFactory(iface):
    from .main_plugin import PlanXDataCube
    return PlanXDataCube(iface)
