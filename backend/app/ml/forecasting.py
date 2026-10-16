"""Demand forecasting engine (pure: no database or HTTP dependencies).

Pipeline for one product:

1. ``build_daily_series`` aggregates records per date and reindexes to a continuous daily
   calendar. Dates with no record are filled with 0 (assumption: a transaction export only
   contains days with sales). The share of filled days is reported and triggers a warning
   above ``HIGH_ZERO_FILL_RATIO`` because a data outage would look like zero demand.
2. If the series has at least ``MIN_EVALUATION_HISTORY_DAYS`` days, the last ``test_size``
   days are held out *chronologically*. Every model is fitted on the training window only
   and forecasts the whole holdout window in one multi-step pass (no peeking at holdout
   actuals), so all models are scored on exactly the same dates.
3. The model with the lowest holdout MAE is selected (ties go to the simpler model), then
   refitted on the full history and used to forecast the requested horizon.
4. With less history than that, no metrics are produced; a moving-average fallback is
   returned and explicitly labelled low confidence. Below ``MIN_FORECAST_HISTORY_DAYS`` no
   forecast is produced at all.

Models:
* ``moving_average`` (baseline): flat forecast equal to the mean of the last 28 days of the
  training window.
* ``seasonal_naive`` (candidate): repeats the last observed week (period 7).
* ``random_forest`` (candidate): RandomForestRegressor on lag (1, 7, 14, 28), trailing
  rolling-mean/std and day-of-week features, forecast recursively one day at a time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from app.ml.metrics import mae, rmse

MIN_FORECAST_HISTORY_DAYS = 14
MIN_EVALUATION_HISTORY_DAYS = 56
MIN_TEST_DAYS = 14
MAX_TEST_DAYS = 28
MIN_HORIZON_DAYS = 1
MAX_HORIZON_DAYS = 90
BASELINE_WINDOW_DAYS = 28
SEASONAL_PERIOD = 7
RF_LAGS = (1, 7, 14, 28)
RF_MIN_TRAIN_ROWS = 14
HIGH_ZERO_FILL_RATIO = 0.10
RANDOM_STATE = 42

# Simpler models first: used to break MAE ties in favour of simplicity.
MODEL_COMPLEXITY_ORDER = ("moving_average", "seasonal_naive", "random_forest")


class InsufficientHistoryError(ValueError):
    pass


class Forecaster(Protocol):
    name: str
    role: str

    def min_train_days(self) -> int: ...
    def fit(self, series: pd.Series) -> Forecaster: ...
    def predict(self, horizon: int) -> np.ndarray: ...


# --------------------------------------------------------------------------- models


class MovingAverageModel:
    """Baseline: mean of the trailing ``window`` days of the training data."""

    name = "moving_average"
    role = "baseline"

    def __init__(self, window: int = BASELINE_WINDOW_DAYS):
        self.window = window
        self.level_: float | None = None

    def min_train_days(self) -> int:
        return 1

    def fit(self, series: pd.Series) -> MovingAverageModel:
        values = series.to_numpy(dtype=float)
        if values.size == 0:
            raise ValueError("cannot fit on an empty series")
        self.level_ = float(values[-self.window :].mean())
        return self

    def predict(self, horizon: int) -> np.ndarray:
        if self.level_ is None:
            raise RuntimeError("model is not fitted")
        return np.full(horizon, self.level_, dtype=float)


class SeasonalNaiveModel:
    """Candidate: repeat the last observed seasonal cycle (weekly by default)."""

    name = "seasonal_naive"
    role = "candidate"

    def __init__(self, period: int = SEASONAL_PERIOD):
        self.period = period
        self.last_cycle_: np.ndarray | None = None

    def min_train_days(self) -> int:
        return 2 * self.period

    def fit(self, series: pd.Series) -> SeasonalNaiveModel:
        values = series.to_numpy(dtype=float)
        if values.size < self.period:
            raise ValueError("series shorter than one seasonal period")
        self.last_cycle_ = values[-self.period :].copy()
        return self

    def predict(self, horizon: int) -> np.ndarray:
        if self.last_cycle_ is None:
            raise RuntimeError("model is not fitted")
        reps = int(np.ceil(horizon / self.period))
        return np.tile(self.last_cycle_, reps)[:horizon].astype(float)


def lag_features(values: np.ndarray, t: int, target_date: date) -> list[float]:
    """Features for predicting ``values[t]`` using only ``values[:t]`` (strictly the past).

    Shared by training and recursive prediction so there is no train/serve skew.
    """
    past = values[:t]
    feats = [float(past[-lag]) for lag in RF_LAGS]
    last7 = past[-7:]
    last28 = past[-28:]
    feats += [
        float(last7.mean()),
        float(last28.mean()),
        float(last7.std()),
        float(target_date.weekday()),
        1.0 if target_date.weekday() >= 5 else 0.0,
    ]
    return feats


FEATURE_NAMES = [f"lag_{lag}" for lag in RF_LAGS] + [
    "rolling_mean_7",
    "rolling_mean_28",
    "rolling_std_7",
    "day_of_week",
    "is_weekend",
]


class RandomForestModel:
    """Candidate: RandomForestRegressor on leakage-free lag/rolling/calendar features."""

    name = "random_forest"
    role = "candidate"

    def __init__(self, n_estimators: int = 100, max_depth: int = 8, min_samples_leaf: int = 3):
        self.params = dict(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=RANDOM_STATE,
            n_jobs=1,
        )
        self.model_: RandomForestRegressor | None = None
        self.history_: np.ndarray | None = None
        self.last_date_: date | None = None

    @staticmethod
    def max_lag() -> int:
        return max(RF_LAGS)

    def min_train_days(self) -> int:
        return self.max_lag() + RF_MIN_TRAIN_ROWS

    def build_training_matrix(self, series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
        values = series.to_numpy(dtype=float)
        dates = [d.date() if hasattr(d, "date") else d for d in series.index]
        rows, targets = [], []
        for t in range(self.max_lag(), len(values)):
            rows.append(lag_features(values, t, dates[t]))
            targets.append(values[t])
        return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)

    def fit(self, series: pd.Series) -> RandomForestModel:
        if len(series) < self.min_train_days():
            raise ValueError(f"random_forest needs at least {self.min_train_days()} days")
        X, y = self.build_training_matrix(series)
        self.model_ = RandomForestRegressor(**self.params).fit(X, y)
        self.history_ = series.to_numpy(dtype=float).copy()
        last = series.index[-1]
        self.last_date_ = last.date() if hasattr(last, "date") else last
        return self

    def predict(self, horizon: int) -> np.ndarray:
        if self.model_ is None or self.history_ is None or self.last_date_ is None:
            raise RuntimeError("model is not fitted")
        values = list(self.history_)
        preds = []
        for step in range(1, horizon + 1):
            target_date = self.last_date_ + timedelta(days=step)
            x = lag_features(np.asarray(values), len(values), target_date)
            yhat = max(0.0, float(self.model_.predict(np.asarray([x]))[0]))
            preds.append(yhat)
            values.append(yhat)  # recursive: later steps use earlier predictions
        return np.asarray(preds, dtype=float)


def default_models() -> list[Forecaster]:
    return [MovingAverageModel(), SeasonalNaiveModel(), RandomForestModel()]


# ------------------------------------------------------------------- data preparation


def build_daily_series(dates, quantities, end_date: date | None = None) -> tuple[pd.Series, int]:
    """Aggregate by date and reindex to a continuous daily calendar (missing -> 0).

    ``end_date`` is the last date covered by the dataset. A product whose last sale is
    earlier is extended with zero-demand days up to it, so trailing days without sales are
    not silently dropped and every product's forecast starts the day after the dataset ends.

    Returns (series, observed_day_count).
    """
    df = pd.DataFrame({"date": pd.to_datetime(list(dates)), "quantity": list(quantities)})
    if df.empty:
        raise InsufficientHistoryError("no sales history for this product")
    daily = df.groupby("date")["quantity"].sum().sort_index()
    last = daily.index.max()
    if end_date is not None:
        end_ts = pd.Timestamp(end_date)
        if end_ts < last:
            raise ValueError("end_date is earlier than the last sales record")
        last = end_ts
    full_index = pd.date_range(daily.index.min(), last, freq="D")
    series = daily.reindex(full_index, fill_value=0.0).astype(float)
    series.index.name = "date"
    return series, int(len(daily))


def holdout_size(n_days: int) -> int:
    return int(min(MAX_TEST_DAYS, max(MIN_TEST_DAYS, n_days // 5)))


# ------------------------------------------------------------------------ results


@dataclass
class ModelEvaluationResult:
    model_name: str
    role: str
    evaluated: bool
    mae: float | None = None
    rmse: float | None = None
    test_samples: int = 0
    train_start: date | None = None
    train_end: date | None = None
    test_start: date | None = None
    test_end: date | None = None
    holdout: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_selected: bool = False


@dataclass
class ForecastResult:
    product_id: str
    horizon_days: int
    history_days: int
    observed_days: int
    history_start: date
    history_end: date
    dates: list[date]
    predictions: list[float]
    total_forecast: float
    selected_model: str
    selection_reason: str
    confidence: str  # "validated" | "low"
    evaluations: list[ModelEvaluationResult]
    warnings: list[str]
    limitations: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------- evaluation


def _d(ts) -> date:
    return ts.date() if hasattr(ts, "date") else ts


def evaluate_models(series: pd.Series, models: list[Forecaster]) -> list[ModelEvaluationResult]:
    """Chronological holdout evaluation; every model is scored on the same test dates."""
    n = len(series)
    test_size = holdout_size(n)
    train, test = series.iloc[:-test_size], series.iloc[-test_size:]
    actual = test.to_numpy(dtype=float)
    results = []
    for model in models:
        base = ModelEvaluationResult(
            model_name=model.name,
            role=model.role,
            evaluated=False,
            train_start=_d(train.index[0]),
            train_end=_d(train.index[-1]),
            test_start=_d(test.index[0]),
            test_end=_d(test.index[-1]),
        )
        if len(train) < model.min_train_days():
            base.warnings.append(
                f"Not evaluated: needs {model.min_train_days()} training days, has {len(train)}."
            )
            results.append(base)
            continue
        model.fit(train)
        predicted = np.clip(model.predict(test_size), 0.0, None)
        base.evaluated = True
        base.mae = mae(actual, predicted)
        base.rmse = rmse(actual, predicted)
        base.test_samples = int(test_size)
        base.holdout = [
            {"date": _d(d), "actual": float(a), "predicted": float(p)}
            for d, a, p in zip(test.index, actual, predicted)
        ]
        results.append(base)
    return results


def select_model(evaluations: list[ModelEvaluationResult]) -> tuple[str, str]:
    """Pick the lowest holdout MAE; ties (within 1e-9) go to the simpler model."""
    scored = [e for e in evaluations if e.evaluated and e.mae is not None]
    if not scored:
        raise ValueError("no evaluated models to select from")
    best = min(scored, key=lambda e: (round(e.mae, 9), MODEL_COMPLEXITY_ORDER.index(e.model_name)))
    baseline = next((e for e in scored if e.role == "baseline"), None)
    if baseline is None or best.model_name == baseline.model_name:
        reason = (
            f"The baseline ({best.model_name}) had the lowest holdout MAE ({best.mae:.2f}); "
            "no candidate improved on it, so the simpler model is used."
        )
    else:
        gain = (baseline.mae - best.mae) / baseline.mae * 100 if baseline.mae > 0 else 0.0
        reason = (
            f"{best.model_name} had the lowest holdout MAE ({best.mae:.2f} vs baseline "
            f"{baseline.mae:.2f}, {gain:.1f}% lower) over the same "
            f"{best.test_samples} holdout days."
        )
        if gain < 5:
            reason += " The improvement is small, so the two models perform similarly."
    best.is_selected = True
    return best.model_name, reason


# ------------------------------------------------------------------------ forecast


BASE_LIMITATIONS = [
    "Point forecasts only; no prediction intervals are produced.",
    "Model selection uses a single chronological holdout window; accuracy may differ in other periods.",
    "Calendar days without sales records are assumed to be zero-demand days.",
    "Promotions, price changes, holidays and historical stockouts (censored demand) are not modelled.",
]


def forecast_product(
    product_id: str,
    dates,
    quantities,
    horizon_days: int,
    models_factory=default_models,
    end_date: date | None = None,
) -> ForecastResult:
    if not MIN_HORIZON_DAYS <= horizon_days <= MAX_HORIZON_DAYS:
        raise ValueError(
            f"horizon_days must be between {MIN_HORIZON_DAYS} and {MAX_HORIZON_DAYS}"
        )
    series, observed_days = build_daily_series(dates, quantities, end_date)
    n = len(series)
    if n < MIN_FORECAST_HISTORY_DAYS:
        raise InsufficientHistoryError(
            f"Product {product_id} has {n} day(s) of history; at least "
            f"{MIN_FORECAST_HISTORY_DAYS} days are required to produce any forecast."
        )

    warnings: list[str] = []
    limitations = list(BASE_LIMITATIONS)
    filled = n - observed_days
    if n and filled / n > HIGH_ZERO_FILL_RATIO:
        warnings.append(
            f"{filled} of {n} days ({filled / n:.0%}) had no sales records and were treated as "
            "zero demand. If these are data gaps, the forecast may be understated."
        )
    if float(series.sum()) == 0.0:
        warnings.append("The product has no recorded sales in its history; the forecast is zero.")

    if n >= MIN_EVALUATION_HISTORY_DAYS:
        evaluations = evaluate_models(series, models_factory())
        selected, reason = select_model(evaluations)
        confidence = "validated"
        test_samples = next(e.test_samples for e in evaluations if e.is_selected)
        if horizon_days > test_samples:
            warnings.append(
                f"Accuracy was validated on a {test_samples}-day holdout; days beyond that in the "
                f"{horizon_days}-day horizon are not directly validated."
            )
    else:
        selected = MovingAverageModel.name
        confidence = "low"
        reason = (
            f"Only {n} days of history (minimum {MIN_EVALUATION_HISTORY_DAYS} for holdout "
            "evaluation). A moving average of the available history is used as a conservative, "
            "unvalidated fallback; no accuracy metrics are reported."
        )
        warnings.append(
            f"Insufficient history for validation: {n} days available, "
            f"{MIN_EVALUATION_HISTORY_DAYS} required. Collect about "
            f"{MIN_EVALUATION_HISTORY_DAYS - n} more days of sales to enable model evaluation."
        )
        evaluations = [
            ModelEvaluationResult(
                model_name=m.name,
                role=m.role,
                evaluated=False,
                warnings=["Not evaluated: insufficient history for a holdout test."],
                is_selected=(m.name == selected),
            )
            for m in models_factory()
        ]

    final_model = next(m for m in models_factory() if m.name == selected)
    final_model.fit(series)
    predictions = np.clip(final_model.predict(horizon_days), 0.0, None)
    last = _d(series.index[-1])
    forecast_dates = [last + timedelta(days=i) for i in range(1, horizon_days + 1)]

    return ForecastResult(
        product_id=product_id,
        horizon_days=horizon_days,
        history_days=n,
        observed_days=observed_days,
        history_start=_d(series.index[0]),
        history_end=last,
        dates=forecast_dates,
        predictions=[round(float(p), 4) for p in predictions],
        total_forecast=round(float(predictions.sum()), 4),
        selected_model=selected,
        selection_reason=reason,
        confidence=confidence,
        evaluations=evaluations,
        warnings=warnings,
        limitations=limitations,
    )
