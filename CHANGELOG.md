# Changelog — PlanX DataCube Lab

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-26

### Added
- Professional PlanX ecosystem icon for QGIS Plugin Manager, toolbar, and Processing provider surfaces.
- QGIS 3.44/QGIS 4 runtime smoke coverage for DataCube dashboard and Processing provider lifecycle.

### Fixed
- Qt6-compatible enum usage in the dashboard and voxel configuration dialog.

### Changed
- README compatibility table now matches metadata with QGIS 3.34 minimum support.

## [0.2.0] — 2026-05-26

### Added
- Production dashboard, grid layer output from cube builder, voxel configuration dialog, and dependency manager with pip installer.
- 59 unit tests for EHSA, forecasting, cube builder, and dependency logic.
- QGIS 3.34+ compatibility baseline.

## [0.1.0] — 2026-05-26

### Added
- Data Cube Builder: vector layer rasterisation and raster stack ingestion into (X×Y×T×V) cubes
- In-memory multi-dimensional DataCube class with JSON serialisation and netCDF4 export
- Emerging Hot Spot Analysis (EHSA) engine with full Getis-Ord Gi* + Mann-Kendall pipeline
- 17-category spatiotemporal pattern classification (ESRI-compatible: New, Consecutive, Intensifying, Persistent, Diminishing, Sporadic, Oscillating, Historical — Hot and Cold)
- Time-Series Forecasting Studio: ARIMA (via statsmodels), Random Forest regressor (via scikit-learn), Exponential Smoothing fallback
- Auto-forecast mode that tries best-available method per cell
- Voxel Configuration Dialog for QGIS 4 native voxel layer bridging
- Full Processing Toolbox provider with 3 algorithms (Create Cube, EHSA, Forecast)
- Dockable multi-tab panel (Cube Builder, EHSA, Forecast)
