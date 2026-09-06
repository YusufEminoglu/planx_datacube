<div align="center">

<img src="icons/icon.png" width="96" alt="PlanX DataCube Lab icon"/>

# PlanX DataCube Lab

**Spatiotemporal data cubes for QGIS — xarray/Dask processing, Emerging Hot Spot Analysis, time-series forecasting and voxel rendering.**

[![QGIS](https://img.shields.io/badge/QGIS-3.34%2B-93b023?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/planx_datacube/)
[![Documentation](https://img.shields.io/badge/📖_Reference_Manual-13a0a0)](https://geophilo.com/planx_datacube/)
[![Version](https://img.shields.io/github/v/tag/YusufEminoglu/planx_datacube?label=version&color=blue)](https://github.com/YusufEminoglu/planx_datacube/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0-orange)](LICENSE)
[![QGIS Plugin Hub](https://img.shields.io/badge/QGIS%20Hub-install-589632?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/planx_datacube/)

</div>

---

## 📖 Documentation

**[Comprehensive Academic Reference Manual](https://geophilo.com/planx_datacube/)** — complete documentation of every feature, parameter, and workflow. Hosted on Web Documentation.


## Why DataCube Lab?

QGIS handles space well and time poorly. DataCube Lab brings the Python data-science stack (`xarray`, `dask`, `netCDF4`, `statsmodels`, `scikit-learn`) into the Processing Toolbox as a unified, lazy-evaluated pipeline: build an (X×Y×T×V) cube from your vector or raster time series, classify how hot spots evolve, forecast each cell, and render the result volumetrically.

## ✨ Features

- **Cube Builder** — vector/raster → multi-dimensional (X×Y×T×V) data cube with optional netCDF4/Zarr export.
- **Space-Time Cube Aggregation** — bin point events into a fishnet × time-step panel (count / sum / mean / max / min); the one-click front door to every analysis tool below, with optional netCDF cube output.
- **Emerging Hot Spot Analysis** — Getis-Ord Gi* with *true* spatial neighbourhoods (fixed distance band or K-nearest) + Mann-Kendall trend → 17 spatiotemporal pattern classes, auto-styled.
- **Local Outlier Analysis (Local Moran's I)** — Anselin LISA cluster/outlier map (High-High, Low-Low, High-Low, Low-High) with a deterministic conditional-permutation significance test.
- **Temporal Trend Analysis** — Mann-Kendall + Theil-Sen slope per location → Increasing / Decreasing / No-trend.
- **Temporal Anomaly Detection** — robust median/MAD (or classic) z-score flags anomalous time steps per location.
- **Forecasting Studio** — ARIMA, Random Forest and Exponential Smoothing per-cell prediction with an auto-fallback chain.
- **Forecast Backtest** — hold-out MAE / RMSE / MAPE per method picks the most trustworthy forecaster before you project forward.
- **Voxel Bridge** — configuration dialog for QGIS 4 native volumetric voxel layer rendering.

## 🚀 Installation

**From the QGIS Plugin Hub (recommended):** `Plugins → Manage and Install Plugins…` → search for **"PlanX DataCube"** → *Install*.

**From a release zip:** download the latest zip from [Releases](https://github.com/YusufEminoglu/planx_datacube/releases) → `Plugins → Install from ZIP`.

Requires QGIS 3.34 or newer (Python 3.9+). Optional extras unlock advanced features:

```bash
pip install netCDF4 statsmodels scikit-learn
```

## 📖 Quick start

1. Install and activate the plugin — tools appear under **Processing Toolbox → PlanX DataCube Lab**.
2. Run **Space-Time Cube Aggregation** on a point/event layer (with a numeric time field) to produce a long-format panel: one row per grid cell per time step.
3. Feed that panel (ID = `cell_id`, Time = `time_step`, Value = `value`) into **Emerging Hot Spot Analysis**, **Local Outlier Analysis**, **Temporal Trend** or **Temporal Anomaly Detection**.
4. Use **Forecast Backtest** to find the best method, then **Time-Series Forecast** to project the series forward.
5. Build a netCDF cube (Cube Builder or Space-Time Cube) and open the **Voxel Bridge** dialog to render it volumetrically in QGIS 4.

All analysis tools share the same panel contract, so any layer with *location id*, *numeric time* and *value* fields works directly — the Space-Time Cube is just the easiest way to create one.

## ⚙️ EHSA pattern classes

<details>
<summary>All 17 classes (click to expand)</summary>

| # | Pattern | # | Pattern |
|---|---------|---|---------|
| 0 | Not Significant | 9 | New Cold Spot |
| 1 | New Hot Spot | 10 | Consecutive Cold Spot |
| 2 | Consecutive Hot Spot | 11 | Intensifying Cold Spot |
| 3 | Intensifying Hot Spot | 12 | Persistent Cold Spot |
| 4 | Persistent Hot Spot | 13 | Diminishing Cold Spot |
| 5 | Diminishing Hot Spot | 14 | Sporadic Cold Spot |
| 6 | Sporadic Hot Spot | 15 | Oscillating Cold Spot |
| 7 | Oscillating Hot Spot | 16 | Historical Cold Spot |
| 8 | Historical Hot Spot | | |

</details>

Full version history: [CHANGELOG.md](CHANGELOG.md)

## 🧩 Part of the PlanX ecosystem

This plugin is one of 15 open-source QGIS plugins for urban planning by the same author:

| Planning & analysis | CAD & production | 3D & visualization |
|---|---|---|
| [PlanX](https://github.com/YusufEminoglu/planx_datacube) — spatial-planning suite | [PlanX CAD Toolset](https://github.com/YusufEminoglu/planx_datacube) — drafting-grade CAD | [PlanX 3D City](https://github.com/YusufEminoglu/planx_datacube) — Three.js city viewer |
| [GeoStats Lab](https://github.com/YusufEminoglu/planx_datacube) — spatial statistics | [EasyFillet](https://github.com/YusufEminoglu/planx_datacube) — tangent-arc fillet | [3D OSM Model](https://github.com/YusufEminoglu/planx_datacube) — OSM → 3D city in browser |
| [Suitability Lab](https://github.com/YusufEminoglu/planx_datacube) — raster MCDA | [Settlement Toolset](https://github.com/YusufEminoglu/planx_datacube) — 9-stage settlement plans | [OSM Quick 3D](https://github.com/YusufEminoglu/planx_datacube) — OSM → native QGIS 3D |
| [DataCube Lab](https://github.com/YusufEminoglu/planx_datacube) — spatiotemporal cubes | [UIP Toolset](https://github.com/YusufEminoglu/planx_datacube) — Turkish master-plan automation | [Urban Procedural 3D](https://github.com/YusufEminoglu/planx_datacube) — parametric zoning lab |
| [Urban Resilience](https://github.com/YusufEminoglu/planx_datacube) — 28 resilience tools | [ParcelFlux](https://github.com/YusufEminoglu/planx_datacube) — parcel subdivision | [CartoLab](https://github.com/YusufEminoglu/planx_datacube) — publication cartography |

## 📜 License & author

GPL-3.0 © [Yusuf Eminoğlu](https://github.com/YusufEminoglu) — bug reports and feature requests welcome in [Issues](https://github.com/YusufEminoglu/planx_datacube/issues).
