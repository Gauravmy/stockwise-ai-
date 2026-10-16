"""Forecast error metrics. Both are expressed in the same units as demand quantity."""

import numpy as np


def _validate(actual, predicted) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if a.shape != p.shape:
        raise ValueError(f"actual and predicted must have the same shape ({a.shape} != {p.shape})")
    if a.size == 0:
        raise ValueError("cannot compute a metric on an empty sample")
    if not (np.isfinite(a).all() and np.isfinite(p).all()):
        raise ValueError("actual and predicted must be finite")
    return a, p


def mae(actual, predicted) -> float:
    """Mean absolute error: mean(|actual - predicted|)."""
    a, p = _validate(actual, predicted)
    return float(np.mean(np.abs(a - p)))


def rmse(actual, predicted) -> float:
    """Root mean squared error: sqrt(mean((actual - predicted)^2)); penalises large errors."""
    a, p = _validate(actual, predicted)
    return float(np.sqrt(np.mean((a - p) ** 2)))
