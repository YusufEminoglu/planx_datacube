<div align="center">

<img src="icons/icon.png" width="96" alt="PlanX DataCube Lab icon"/>

# PlanX DataCube Lab

**Spatiotemporal data cubes for QGIS — xarray/Dask processing, Emerging Hot Spot Analysis, time-series forecasting and voxel rendering.**

[![QGIS](https://img.shields.io/badge/QGIS-3.34%2B-93b023?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/planx_datacube/)
[![Version](https://img.shields.io/github/v/tag/YusufEminoglu/planx_datacube?label=version&color=blue)](https://github.com/YusufEminoglu/planx_datacube/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0-orange)](LICENSE)
[![QGIS Plugin Hub](https://img.shields.io/badge/QGIS%20Hub-install-589632?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/planx_datacube/)

</div>

---

## Why DataCube Lab?

QGIS handles space well and time poorly. DataCube Lab brings the Python data-science stack (`xarray`, `dask`, `netCDF4`, `statsmodels`, `scikit-learn`) into the Processing Toolbox as a unified, lazy-evaluated pipeline: build an (X×Y×T×V) cube from your vector or raster time series, classify how hot spots evolve, forecast each cell, and render the result volumetrically.

## ✨ Features

- **Cube Builder** — vector/raster → multi-dimensional (X×Y×T×V) data cube with optional netCDF4/Zarr export.
- **Emerging Hot Spot Analysis** — Getis-Ord Gi* + Mann-Kendall trend → 17 spatiotemporal pattern classes.
- **Forecasting Studio** — ARIMA, Random Forest and Exponential Smoothing per-cell prediction.
- **Auto-forecast** — ARIMA → RF → ES fallback chain for maximum robustness on messy series.
- **Voxel Bridge** — configuration dialog for QGIS 4 native volumetric voxel layer rendering.
- **Lazy evaluation** — Dask-backed processing keeps large cubes workable on a laptop.

## 🚀 Installation

**From the QGIS Plugin Hub (recommended):** `Plugins → Manage and Install Plugins…` → search for **"PlanX DataCube"** → *Install*.

**From a release zip:** download the latest zip from [Releases](https://github.com/YusufEminoglu/planx_datacube/releases) → `Plugins → Install from ZIP`.

Requires QGIS 3.34 or newer (Python 3.9+). Optional extras unlock advanced features:

```bash
pip install netCDF4 statsmodels scikit-learn
```

## 📖 Quick start

1. Install and activate the plugin — tools appear under **Processing Toolbox → PlanX DataCube Lab**.
2. Run **Cube Builder** on a vector or raster time series to create the data cube.
3. Run **Emerging Hot Spot Analysis** on the cube to classify each cell's pattern.
4. Run **Forecasting Studio** (or **Auto-forecast**) to project the series forward.
5. Open the **Voxel Bridge** dialog to render the cube volumetrically in QGIS 4.

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
| [PlanX](https://github.com/YusufEminoglu/PlanX) — spatial-planning suite | [PlanX CAD Toolset](https://github.com/YusufEminoglu/PlanX-CAD) — drafting-grade CAD | [PlanX 3D City](https://github.com/YusufEminoglu/planx_3d_city) — Three.js city viewer |
| [GeoStats Lab](https://github.com/YusufEminoglu/planx_geostats) — spatial statistics | [EasyFillet](https://github.com/YusufEminoglu/EasyFillet) — tangent-arc fillet | [3D OSM Model](https://github.com/YusufEminoglu/osm_3d_model) — OSM → 3D city in browser |
| [Suitability Lab](https://github.com/YusufEminoglu/planx_suitability_lab) — raster MCDA | [Settlement Toolset](https://github.com/YusufEminoglu/PlanX-Settlement) — 9-stage settlement plans | [OSM Quick 3D](https://github.com/YusufEminoglu/osm_quick_3d) — OSM → native QGIS 3D |
| [DataCube Lab](https://github.com/YusufEminoglu/planx_datacube) — spatiotemporal cubes | [UIP Toolset](https://github.com/YusufEminoglu/PlanX-UIP) — Turkish master-plan automation | [Urban Procedural 3D](https://github.com/YusufEminoglu/planx_urban_procedural_3d) — parametric zoning lab |
| [Urban Resilience](https://github.com/YusufEminoglu/planx_urban_resilience) — 28 resilience tools | [ParcelFlux](https://github.com/YusufEminoglu/parcelflux) — parcel subdivision | [CartoLab](https://github.com/YusufEminoglu/planx_cartolab) — publication cartography |

## 📜 License & author

GPL-3.0 © [Yusuf Eminoğlu](https://github.com/YusufEminoglu) — bug reports and feature requests welcome in [Issues](https://github.com/YusufEminoglu/planx_datacube/issues).
