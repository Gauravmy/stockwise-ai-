import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml.forecasting import (
    MIN_EVALUATION_HISTORY_DAYS,
    InsufficientHistoryError,
    ModelEvaluationResult,
    MovingAverageModel,
    RandomForestModel,
    SeasonalNaiveModel,
    build_daily_series,
    evaluate_models,
    forecast_product,
    holdout_size,
    lag_features,
    select_model,
)
from app.ml.metrics import mae, rmse

START = date(2024, 1, 1)


def dates(n, start=START):
    return [start + timedelta(days=i) for i in range(n)]


def series(values, start=START):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


# ---------------------------------------------------------------- metrics


def test_mae_and_rmse_known_values():
    actual = [1, 2, 3, 4]
    pred = [2, 2, 2, 8]
    assert mae(actual, pred) == pytest.approx((1 + 0 + 1 + 4) / 4)
    assert rmse(actual, pred) == pytest.approx(math.sqrt((1 + 0 + 1 + 16) / 4))
    assert rmse(actual, pred) >= mae(actual, pred)


def test_metrics_reject_bad_input():
    with pytest.raises(ValueError):
        mae([], [])
    with pytest.raises(ValueError):
        rmse([1, 2], [1])
    with pytest.raises(ValueError):
        mae([1, float("nan")], [1, 1])


def test_perfect_prediction_zero_error():
    assert mae([3, 3], [3, 3]) == 0
    assert rmse([3, 3], [3, 3]) == 0


# ---------------------------------------------------------------- preparation


def test_build_daily_series_fills_missing_dates_and_aggregates():
    s, observed = build_daily_series(
        [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 4)], [2, 3, 7]
    )
    assert s.tolist() == [5, 0, 0, 7]
    assert observed == 2


def test_holdout_size_bounds():
    assert holdout_size(56) == 14
    assert holdout_size(100) == 20
    assert holdout_size(1000) == 28


# ---------------------------------------------------------------- models


def test_moving_average_baseline_uses_trailing_window_only():
    m = MovingAverageModel(window=3).fit(series([100, 1, 2, 3]))
    assert m.predict(2).tolist() == [2.0, 2.0]


def test_seasonal_naive_repeats_last_week():
    week = [1, 2, 3, 4, 5, 6, 7]
    m = SeasonalNaiveModel().fit(series([9] * 7 + week))
    assert m.predict(10).tolist() == week + week[:3]


def test_lag_features_do_not_use_future_values():
    values = np.arange(60, dtype=float)
    t = 40
    base = lag_features(values, t, date(2024, 2, 10))
    tampered = values.copy()
    tampered[t:] = 9999  # change the target and everything after it
    assert lag_features(tampered, t, date(2024, 2, 10)) == base
    assert base[0] == values[t - 1]  # lag_1


def test_random_forest_training_matrix_targets_align_with_lags():
    s = series(np.arange(50, dtype=float))
    X, y = RandomForestModel().build_training_matrix(s)
    assert len(X) == 50 - 28
    # lag_1 of each row is exactly the previous target value -> no leakage of y into X
    assert np.allclose(X[:, 0], y - 1)


def test_random_forest_is_reproducible_and_non_negative():
    rng = np.random.default_rng(0)
    vals = rng.poisson(5, 120).astype(float)
    p1 = RandomForestModel().fit(series(vals)).predict(14)
    p2 = RandomForestModel().fit(series(vals)).predict(14)
    assert np.array_equal(p1, p2)
    assert (p1 >= 0).all()


# ---------------------------------------------------------------- evaluation


def test_evaluation_is_chronological_and_uses_same_dates_for_all_models():
    rng = np.random.default_rng(1)
    s = series(rng.poisson(10, 100).astype(float))
    evals = evaluate_models(s, [MovingAverageModel(), SeasonalNaiveModel(), RandomForestModel()])
    test_n = holdout_size(100)
    for e in evals:
        assert e.evaluated
        assert e.test_samples == test_n
        assert e.train_end < e.test_start
        assert e.test_end == s.index[-1].date()
        assert [h["date"] for h in e.holdout] == [d.date() for d in s.index[-test_n:]]
    # Metrics must be computed from the stored holdout points.
    for e in evals:
        a = [h["actual"] for h in e.holdout]
        p = [h["predicted"] for h in e.holdout]
        assert e.mae == pytest.approx(mae(a, p))
        assert e.rmse == pytest.approx(rmse(a, p))


def test_baseline_evaluation_ignores_holdout_values():
    """Changing holdout actuals must not change baseline predictions (no leakage)."""
    vals = [10.0] * 80
    s1 = series(vals)
    s2 = series(vals[:-holdout_size(80)] + [500.0] * holdout_size(80))
    e1 = evaluate_models(s1, [MovingAverageModel()])[0]
    e2 = evaluate_models(s2, [MovingAverageModel()])[0]
    assert [h["predicted"] for h in e1.holdout] == [h["predicted"] for h in e2.holdout]
    assert e2.mae == pytest.approx(490.0)


def test_select_model_prefers_lowest_mae_and_simpler_on_ties():
    def ev(name, role, m):
        return ModelEvaluationResult(model_name=name, role=role, evaluated=True, mae=m, rmse=m, test_samples=14)

    name, _ = select_model([ev("moving_average", "baseline", 2.0), ev("random_forest", "candidate", 1.0)])
    assert name == "random_forest"
    name, reason = select_model([ev("moving_average", "baseline", 1.0), ev("random_forest", "candidate", 1.0)])
    assert name == "moving_average"
    assert "baseline" in reason


def test_weekly_pattern_candidate_beats_baseline():
    pattern = [30, 30, 30, 30, 30, 2, 2]
    vals = (pattern * 20)[:140]
    result = forecast_product("W", dates(140), vals, 14)
    assert result.selected_model in ("seasonal_naive", "random_forest")
    baseline = next(e for e in result.evaluations if e.role == "baseline")
    selected = next(e for e in result.evaluations if e.is_selected)
    assert selected.mae < baseline.mae
    assert result.confidence == "validated"


# ---------------------------------------------------------------- forecast_product


def test_constant_demand_forecast_is_constant():
    result = forecast_product("C", dates(100), [7.0] * 100, 30)
    assert result.selected_model == "moving_average"  # tie -> simplest
    assert result.predictions == pytest.approx([7.0] * 30)
    assert result.total_forecast == pytest.approx(210.0)
    assert all(e.mae == pytest.approx(0.0) for e in result.evaluations if e.evaluated)


def test_zero_demand_forecast_is_zero_with_warning():
    result = forecast_product("Z", dates(80), [0.0] * 80, 7)
    assert result.total_forecast == 0
    assert any("no recorded sales" in w for w in result.warnings)


def test_short_history_is_low_confidence_without_metrics():
    result = forecast_product("S", dates(30), [5.0] * 30, 14)
    assert result.confidence == "low"
    assert all(not e.evaluated and e.mae is None and e.rmse is None for e in result.evaluations)
    assert any("Insufficient history" in w for w in result.warnings)
    assert len(result.predictions) == 14


def test_too_short_history_raises():
    with pytest.raises(InsufficientHistoryError):
        forecast_product("T", dates(5), [1] * 5, 7)


def test_horizon_validation():
    with pytest.raises(ValueError):
        forecast_product("H", dates(60), [1] * 60, 0)
    with pytest.raises(ValueError):
        forecast_product("H", dates(60), [1] * 60, 91)


def test_forecast_dates_follow_history():
    result = forecast_product("D", dates(60), [1] * 60, 3)
    assert result.history_end == START + timedelta(days=59)
    assert result.dates == [START + timedelta(days=60 + i) for i in range(3)]


def test_horizon_longer_than_holdout_warns():
    result = forecast_product("L", dates(MIN_EVALUATION_HISTORY_DAYS), [3] * MIN_EVALUATION_HISTORY_DAYS, 60)
    assert any("not directly validated" in w for w in result.warnings)


def test_multiple_products_are_independent():
    a = forecast_product("A", dates(70), [10] * 70, 7)
    b = forecast_product("B", dates(70), [1] * 70, 7)
    a_again = forecast_product("A", dates(70), [10] * 70, 7)
    assert a.predictions == a_again.predictions
    assert a.predictions != b.predictions


def test_sparse_history_warns_about_zero_filling():
    ds = [START + timedelta(days=i) for i in range(0, 90, 3)]
    result = forecast_product("P", ds, [9] * len(ds), 7)
    assert result.history_days == 88
    assert any("treated as zero demand" in w for w in result.warnings)


def test_series_extends_to_dataset_end_with_zero_days():
    s, observed = build_daily_series([date(2024, 1, 1), date(2024, 1, 2)], [4, 6], end_date=date(2024, 1, 5))
    assert s.tolist() == [4, 6, 0, 0, 0]
    assert observed == 2
    with pytest.raises(ValueError):
        build_daily_series([date(2024, 1, 3)], [1], end_date=date(2024, 1, 1))


def test_forecast_starts_after_dataset_end_for_product_with_trailing_gap():
    """Regression: an intermittent product whose last sale is before the dataset end must
    not start its forecast inside the historical period."""
    ds = dates(70)
    result = forecast_product("I", ds[:-3], [2] * 67, 7, end_date=ds[-1])
    assert result.history_end == ds[-1]
    assert result.dates[0] == ds[-1] + timedelta(days=1)
    assert result.history_days == 70
