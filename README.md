# PlanX DataCube Lab — Next-Generation Spatiotemporal Analysis Engine

**Multi-dimensional data cubes, Emerging Hot Spot Analysis, and time-series forecasting for QGIS.**

DataCube Lab fundamentally upgrades QGIS's spatiotemporal analysis capabilities by
bringing the Python data-science stack (`xarray`, `dask`, `netCDF4`, `statsmodels`,
`scikit-learn`) into the Processing Toolbox as a unified, lazy-evaluated pipeline.

## Features

| Module | Description |
|--------|-------------|
| **Cube Builder** | Vector/raster → (X×Y×T×V) multi-dimensional data cube with optional netCDF4/Zarr export |
| **Emerging Hot Spot Analysis** | Getis-Ord Gi* + Mann-Kendall → 17 spatiotemporal pattern classes |
| **Forecasting Studio** | ARIMA, Random Forest, Exponential Smoothing — per-cell time-series prediction |
| **Auto-forecast** | Tries ARIMA → RF → ES fallback chain for maximum robustness |
| **Voxel Bridge** | Configuration dialog for QGIS 4 native volumetric voxel layer rendering |

## EHSA Pattern Classes

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

## Installation

```bash
pip install netCDF4 statsmodels scikit-learn  # optional: enables advanced features
```

Then:
1. Download `.zip` from [Releases](https://github.com/YusufEminoglu/planx_datacube/releases).
2. QGIS → Plugins → Manage → Install from ZIP.
3. Activate **PlanX DataCube Lab**.

## Compatibility

| Requirement | Value |
|-------------|-------|
| QGIS minimum | 3.34 |
| QGIS maximum | 4.99 |
| Python | 3.9+ |
| License | GPL-3.0 |

## Architecture

```
planx_datacube/
  core/             # Mathematical engines (cube builder, EHSA, forecasting)
  processing/       # QgsProcessingAlgorithm implementations
  ui/               # Dock panel and voxel config dialog
```

## Author

**Yusuf Eminoglu** — [GitHub](https://github.com/YusufEminoglu) | yusuf.eminoglu@deu.edu.tr

[Changelog](CHANGELOG.md) · [PlanX monorepo](https://github.com/YusufEminoglu)
