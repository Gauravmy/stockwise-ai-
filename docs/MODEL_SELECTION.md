# Model selection reasoning

This document explains which forecasting models are implemented, how they are compared and why. Code references are in `backend/app/ml/forecasting.py`.

## Goal and constraints

We need daily demand forecasts per product, 1–90 days ahead, to drive reorder decisions. The constraints:

- History is short to medium, from weeks to about 18 months.
- There is one series per product, with no external drivers.
- Everything runs locally and must be explainable, reproducible and quick (seconds per product).
- The candidate must be **compared fairly** with a simple baseline. A more complex model is only used when holdout evidence supports it.

## Models

| Name | Role | Why it is included |
|---|---|---|
| `moving_average` (28-day trailing mean) | **Baseline** | Simple, robust and hard to beat on noisy or level series. It is the reference every other model must improve on. Its training window is defined: the last 28 days of the training data, or all of it if shorter. |
| `seasonal_naive` (repeat last 7 days) | Candidate | The classic benchmark for series with a weekly cycle. It needs no fitting and shows whether a weekday pattern exists. |
| `random_forest` (`RandomForestRegressor`) | Candidate | Captures non-linear combinations of recent level, weekly lags and day of week. It needs no feature scaling and is deterministic with `random_state=42`. |

**Random forest features** (`lag_features`), computed only from values strictly before the target day:

- lags 1, 7, 14 and 28
- trailing 7-day and 28-day means
- trailing 7-day standard deviation
- day of week and a weekend flag

**Hyperparameters:** 100 trees, `max_depth=8` and `min_samples_leaf=3`. These are conservative settings to limit overfitting on a few hundred rows. They were **not** tuned on the holdout, because that would leak test information into model choice.

Alternatives considered and not implemented:

| Alternative | Reason |
|---|---|
| ARIMA / ETS (statsmodels) | Extra dependency and per-series parameter search. Seasonal-naive plus a moving average already cover the "trend-free seasonal" and "level" cases for this data. A good next step would be ETS with automatic selection. |
| Gradient boosting (LightGBM/XGBoost) | Extra native dependency, and little expected gain over a random forest at this data size. |
| Prophet | Heavy dependency, and slow per product. |
| Global model across products | Would help short-history products but makes leakage control and explanation harder. Listed as a future improvement. |

## Leakage prevention

1. **Chronological split.** The holdout is the most recent `clip(n // 5, 14, 28)` days. Random splits are never used.
2. **Training-only fitting.** Every model is fitted on the training window only. The baseline's mean, the seasonal cycle and the forest's training matrix are all built from training data.
3. **Strictly-past features.** `lag_features(values, t, date)` reads only `values[:t]`. `test_lag_features_do_not_use_future_values` overwrites `values[t:]` and asserts the features are unchanged.
4. **No peeking during evaluation.** The holdout is predicted in **one multi-step pass**, with recursive prediction for the random forest. Holdout actual values never feed back into the features, which matches how the model is used in production. `test_baseline_evaluation_ignores_holdout_values` changes the holdout actual values and asserts the predictions do not move.
5. **No preprocessing fitted on test data.** There is no scaler. Zero-filling missing dates is deterministic and does not depend on the target values.

## Metrics and selection rule

- **Metrics:** MAE and RMSE, both on the same holdout dates for every model (`evaluate_models`).
- **Selection rule:** `select_model` picks the lowest MAE. Ties within 1e-9 go to the simpler model, in the order `moving_average < seasonal_naive < random_forest`.
- **Why MAE as the primary metric:** daily demand errors translate roughly linearly into stock cost, and MAE is robust to the occasional promotion spike. RMSE is reported alongside it to reveal models that make occasional large misses.
- **Selection reason:** stored with the run and shown in the UI, including the percentage gain over the baseline. Gains under 5% are explicitly called "small".
- **Final fit:** the chosen model is refitted on the **full** history before forecasting the requested horizon.

## Insufficient history policy

| History (days) | Behaviour |
|---|---|
| < 14 | No forecast: `422 insufficient_history`. Two weeks is the minimum for a sensible average level. |
| 14–55 | Moving-average fallback, `confidence = "low"`, every evaluation marked `evaluated: false` with `null` metrics, and a warning stating how many more days are needed |
| ≥ 56 | Full evaluation: at least 42 training days, which covers the forest's 28-day lags plus 14 training rows, and at least 14 test days |

## Results on the synthetic sample

Holdout 2025-06-03 → 2025-06-30, 28 days, trained on 2024-01-01 → 2025-06-02. Values are MAE / RMSE in units per day, produced by `python -m scripts.seed --reset`:

| Product (pattern) | Moving average | Seasonal naive | Random forest | Selected |
|---|---|---|---|---|
| SKU-1001 (weekly) | 6.57 / 8.62 | 6.00 / 6.92 | **4.13 / 5.08** | random_forest (−37%) |
| SKU-1002 (trend up) | **4.62 / 5.88** | 5.43 / 6.57 | 5.01 / 6.64 | moving_average |
| SKU-1003 (annual) | 3.43 / 4.39 | 3.68 / 4.52 | **3.41** / 4.43 | random_forest (gain < 1%, flagged small; RMSE slightly worse) |
| SKU-1004 (intermittent) | **0.49 / 0.67** | 0.82 / 1.09 | 0.55 / 0.69 | moving_average |
| SKU-1005 (trend down) | **2.43 / 2.85** | 3.43 / 4.10 | 2.54 / 3.19 | moving_average |
| SKU-1006 (weekday) | 10.43 / 12.32 | 6.64 / 8.84 | **3.90 / 5.22** | random_forest (−63%) |
| SKU-1007 (promo) | 2.63 / 3.94 | **2.18 / 3.63** | 2.55 / 3.92 | seasonal_naive |
| SKU-1008 (40 days) | — | — | — | moving_average, low confidence |

What the results show:

- On the series with strong weekly structure (SKU-1001, SKU-1006), the random forest beats the baseline clearly.
- On trend, intermittent and noisy series, the **baseline wins**, so the more complex model is not used.
- SKU-1003 is a borderline case. The forest's MAE is 0.6% lower but its RMSE is higher. The rule still selects it, and the UI explains that the improvement is small. With a single 28-day holdout, a difference that small is not meaningful. Rolling-origin backtesting would settle it, and is listed as an improvement.
- These numbers come from **synthetic** data with known patterns. They show that the pipeline works, not how it would perform on real demand.

## Known limitations

- A single holdout window. Accuracy beyond 28 days ahead is not directly validated, and the forecast warns when the horizon is longer than the holdout.
- No prediction intervals.
- Recursive forecasts can drift over long horizons.
- Historical stockouts (censored demand), promotions, prices and holidays are not modelled.
- The zero-fill assumption understates demand if missing dates are actually data outages. The share of filled days is reported, and a warning appears above 10%.
