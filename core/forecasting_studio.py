# -*- coding: utf-8 -*-
"""
Time-Series Forecasting Studio.

Per-cell parallel forecasting using:
  - ARIMA / SARIMAX (via statsmodels, if available)
  - Random Forest time-series regressor (via scikit-learn, if available)
  - Simple exponential smoothing (pure-Python fallback)
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Pure-Python exponential smoothing
# ---------------------------------------------------------------------------

def _clean_series(series):
    """Filter None, NaN, inf from a series returning float list."""
    return [float(v) for v in series if v is not None and math.isfinite(float(v))]


def exponential_smoothing(
    series: List[float],
    alpha: float = 0.3,
    steps_ahead: int = 5,
) -> List[float]:
    """
    Simple exponential smoothing forecast.

    Returns `steps_ahead` forecast values + the fitted series.
    """
    clean = _clean_series(series)
    if len(clean) < 2:
        return [clean[-1] if clean else 0.0] * steps_ahead

    fitted = [clean[0]]
    for i in range(1, len(clean)):
        fitted.append(alpha * clean[i] + (1 - alpha) * fitted[-1])

    forecast = []
    last = fitted[-1]
    for _ in range(steps_ahead):
        forecast.append(last)

    return forecast


# ---------------------------------------------------------------------------
# ARIMA wrapper (statsmodels, optional)
# ---------------------------------------------------------------------------

def arima_forecast(
    series: List[float],
    order: Tuple[int, int, int] = (1, 0, 1),
    steps_ahead: int = 5,
) -> Tuple[Optional[List[float]], str]:
    """
    Fit ARIMA model and forecast. Falls back to exponential smoothing.

    Returns (forecast_values, method_name).
    """
    clean = _clean_series(series)
    if len(clean) < 8:
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"

    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(clean, order=order)
        fitted = model.fit()
        forecast = fitted.forecast(steps=steps_ahead)
        return list(forecast), "ARIMA"
    except ImportError:
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"
    except Exception:
        # ARIMA may fail to converge for some series
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"


# ---------------------------------------------------------------------------
# Random Forest time-series regressor (scikit-learn, optional)
# ---------------------------------------------------------------------------

def random_forest_forecast(
    series: List[float],
    lookback: int = 5,
    steps_ahead: int = 5,
    n_estimators: int = 100,
) -> Tuple[Optional[List[float]], str]:
    """
    Sliding-window Random Forest time-series forecast.

    Converts the series into supervised (X, y) pairs using a lag window,
    fits a RandomForestRegressor, and recursively forecasts.
    """
    clean = _clean_series(series)
    if len(clean) < lookback + 5:
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"

    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
    except ImportError:
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"

    # build supervised dataset
    X, y = [], []
    for i in range(len(clean) - lookback):
        X.append(clean[i:i + lookback])
        y.append(clean[i + lookback])

    if len(X) < 4:
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"

    X_arr = np.array(X)
    y_arr = np.array(y)

    model = RandomForestRegressor(n_estimators=n_estimators, random_state=42)
    model.fit(X_arr, y_arr)

    # recursive forecast
    window = list(clean[-lookback:])
    forecast = []
    for _ in range(steps_ahead):
        pred = model.predict(np.array([window]))[0]
        forecast.append(float(pred))
        window.pop(0)
        window.append(pred)

    return forecast, "RandomForest"


# ---------------------------------------------------------------------------
# Forecast orchestrator
# ---------------------------------------------------------------------------

def forecast_cell_series(
    series: List[float],
    method: str = "auto",
    steps_ahead: int = 5,
) -> Tuple[List[float], str]:
    """
    Run the best available forecaster for a single grid cell's time series.

    Parameters
    ----------
    series : list[float]
        Time-ordered values for one cell.
    method : str
        "arima", "random_forest", "exponential", or "auto" (best available).
    steps_ahead : int
        Number of future steps to predict.

    Returns
    -------
    (forecast_values, method_used)
    """
    clean = _clean_series(series)
    if not clean:
        return [0.0] * steps_ahead, "none"
    if len(clean) < 2:
        return [clean[-1]] * steps_ahead, "constant"

    if method == "exponential":
        return exponential_smoothing(clean, steps_ahead=steps_ahead), "exponential_smoothing"

    if method == "arima":
        return arima_forecast(clean, steps_ahead=steps_ahead)

    if method == "random_forest":
        return random_forest_forecast(clean, steps_ahead=steps_ahead)

    # auto: try ARIMA first, fall back to RF, then exponential
    forecast, used = arima_forecast(clean, steps_ahead=steps_ahead)
    if used == "exponential_smoothing":
        forecast, used = random_forest_forecast(clean, steps_ahead=steps_ahead)

    return forecast, used


# ---------------------------------------------------------------------------
# Accuracy metrics & backtesting
# ---------------------------------------------------------------------------

def forecast_metrics(actual: List[float], predicted: List[float]) -> Tuple[float, float, float]:
    """
    Compute (MAE, RMSE, MAPE %) between aligned actual and predicted series.

    MAPE skips points where the actual value is ~0 to avoid division blow-up;
    if every actual is ~0 it returns ``nan`` for MAPE.
    """
    n = min(len(actual), len(predicted))
    if n == 0:
        return math.nan, math.nan, math.nan
    abs_err = [abs(actual[i] - predicted[i]) for i in range(n)]
    sq_err = [(actual[i] - predicted[i]) ** 2 for i in range(n)]
    mae = sum(abs_err) / n
    rmse = math.sqrt(sum(sq_err) / n)
    pcts = [abs((actual[i] - predicted[i]) / actual[i]) for i in range(n)
            if abs(actual[i]) > 1e-9]
    mape = (100.0 * sum(pcts) / len(pcts)) if pcts else math.nan
    return mae, rmse, mape


# Methods compared during a backtest (auto is excluded — it just picks one).
BACKTEST_METHODS = ("exponential", "arima", "random_forest")


def backtest_series(
    series: List[float],
    holdout: int = 3,
    methods: Tuple[str, ...] = BACKTEST_METHODS,
) -> dict:
    """
    Hold out the last ``holdout`` observations, forecast them with each
    method from the remaining history, and score the predictions.

    Returns::

        {
          "n_train": int,
          "n_test": int,
          "scores": {method: (mae, rmse, mape)},
          "best_method": str,      # lowest RMSE (or "none")
          "best_rmse": float,
        }

    A method that cannot run on the short training slice silently falls back
    to exponential smoothing inside :func:`forecast_cell_series`, so the
    reported method name reflects what actually produced the numbers.
    """
    clean = _clean_series(series)
    n = len(clean)
    result = {"n_train": 0, "n_test": 0, "scores": {},
              "best_method": "none", "best_rmse": math.nan}
    if n < holdout + 2 or holdout < 1:
        return result

    train = clean[:-holdout]
    test = clean[-holdout:]
    result["n_train"] = len(train)
    result["n_test"] = len(test)

    best_rmse = math.inf
    best_method = "none"
    for method in methods:
        forecast, used = forecast_cell_series(train, method=method, steps_ahead=holdout)
        mae, rmse, mape = forecast_metrics(test, forecast)
        result["scores"][used] = (mae, rmse, mape)
        if math.isfinite(rmse) and rmse < best_rmse:
            best_rmse = rmse
            best_method = used

    result["best_method"] = best_method
    result["best_rmse"] = best_rmse if math.isfinite(best_rmse) else math.nan
    return result
