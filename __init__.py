# -*- coding: utf-8 -*-
"""
PlanX DataCube Lab — Spatiotemporal analysis engine for QGIS.
Multi-dimensional (X×Y×T×V) data cube construction, Emerging Hot Spot
Analysis, time-series forecasting, and an integrated 3D voxel preview.

classFactory returns the PlanXDataCube instance.
"""


def classFactory(iface):
    from .main_plugin import PlanXDataCube
    return PlanXDataCube(iface)
