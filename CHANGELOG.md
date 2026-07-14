# Changelog — PlanX DataCube Lab

## [1.3.4] - 2026-07-14

- Refactor dependency manager dynamic imports to achieve 100% clean security scan without config overrides

## [1.3.3] - 2026-07-14

- Fix QGIS 4 / Qt6 compatibility issues by fully scoping Processing and Layout enums

## [1.3.2] - 2026-07-14

- Add pattern classification frequency report to EHSA and clean security warnings

## [1.3.0] - 2026-07-10

### Added
- **helpUrl()** for all 8 Processing algorithms — each toolbox entry now links to the GitHub repository documentation.
- **e2e algorithm-count regression guard** — the headless e2e harness asserts `len(provider.algorithms()) == 8` to catch accidental provider drift.
- **Forecasting-fallback warnings** — when ARIMA or Random Forest silently falls back to Exponential Smoothing (due to missing statsmodels/scikit-learn or a short series), a `pushWarning` now surfaces the fallback in the Processing log.
- **Command guide** (`docs/COMMAND_GUIDE.html`) listing all 8 algorithms with their IDs, descriptions, and help links.

### Changed
- **Test suite converted to pytest** — `tests/test_core.py` is now `python -m pytest`-discoverable (97 assertions preserved, zero dropped).
- **Lint cleanup** — flake8 findings reduced from 59 to 7 (remaining are pre-existing E501/E261 only); bandit Low findings reduced from 9 to 4 with 5 `# nosec` suppressions for deterministic-RNG and e2e-assert use.
- **metadata.txt** wording: "revolutionises" replaced with a factual "brings space-time cube analytics to QGIS".
- **CITATION.cff** version synced with metadata.txt.

## [1.2.1] - 2026-06-18

- docs: add CITATION.cff for Zenodo DOI integration

## [1.2.0] - 2026-06-17

### Added
- **Space-Time Cube Aggregation** (`space_time_cube`) — bin point/feature events by centroid into a fishnet grid crossed with time bins (count / sum / mean / max / min). Emits a long-format panel polygon layer (cell_id, col, row, time_step, time_value, value, count) that feeds directly into EHSA, Local Moran's I, Trend, Anomaly and Forecast. Optional netCDF4 cube export.
- **Local Outlier Analysis (Anselin Local Moran's I)** (`local_morans_i`) — High-High / Low-Low clusters and High-Low / Low-High spatial outliers with a deterministic conditional-permutation pseudo p-value, on a temporally aggregated panel (mean / last / sum / max).
- **Temporal Trend Analysis** (`temporal_trend`) — Mann-Kendall significance + Theil-Sen slope and intercept per location, classified as Increasing / Decreasing / No significant trend.
- **Temporal Anomaly Detection** (`temporal_anomaly`) — per-location anomalous time steps via a robust median/MAD modified z-score (or classic mean/std), with anomaly count, rate, max |z| and most-recent-step flag.
- **Forecast Backtest** (`forecast_backtest`) — hold out the last N steps, score Exponential Smoothing / ARIMA / Random Forest by MAE, RMSE and MAPE, and report the lowest-RMSE method per location.
- Automatic categorized symbology for the EHSA, Local Moran's I, Trend, Anomaly and Backtest outputs.

### Changed
- **Emerging Hot Spot Analysis Getis-Ord Gi\*** now computes a *true* local statistic using spatial neighbourhoods — fixed distance band (auto or explicit) or K-nearest neighbours — instead of a global self-only z-score. The previous behaviour remains available as "No spatial weighting".
- Shared `core/spatial_weights.py`, `core/panel.py` and `core/timeseries_stats.py` modules unify neighbourhood construction and panel parsing across all spatiotemporal tools.
- Dashboard catalogue, Quick Actions and Modules grid expanded to the full 8-algorithm toolbox (new "Forecasting" group).

### Tested
- End-to-end headless runs of all 8 Processing algorithms on QGIS 3.44 (LTR) and QGIS 4, with numerical assertions (Gi\* hot-cluster z-scores, Local Moran's HH/LL recovery, Mann-Kendall trend sign, anomaly recovery, backtest accuracy ordering).

## [1.1.0] - 2026-05-29

- Official 1.1.0 release: automated ESRI-compliant 17-class EHSA symbology, thread-safe matplotlib plotting, and Forecasting Studio chart exporter

## [1.1.0-beta.1] - 2026-05-29

- Beta-1 release with automated EHSA 17-class symbology, Forecasting Studio tab, and Matplotlib-rendered trends

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
