# Technical interview preparation: StockWise AI

Each answer has three parts:

- **Simple:** what to say first.
- **Detail:** what to add if they dig deeper.
- **In the code:** where it lives in the repository.

"Implemented" means the repository does it today. "Future" means it does not.

---

## Part A: Pitches

### 60-second introduction

"StockWise AI is a full-stack demand forecasting and inventory tool. You upload historical sales as CSV. The backend validates every row: it rejects bad dates or negative quantities, flags exact duplicates and sums same-day transactions. Each upload is stored as a versioned dataset in SQLite.

For each product, I compare a moving-average baseline with two candidates, a weekly seasonal-naive model and a random forest on lag features. All three are scored on the same chronological holdout with MAE and RMSE, and the lowest MAE wins. On the synthetic sample the baseline actually wins on three of seven products, so I don't assume complexity helps.

The forecast then drives an explainable reorder policy: lead-time demand plus safety stock gives the reorder point, and an order-up-to target gives the quantity, rounded to MOQ and pack size. Every recommendation comes with a plain-English explanation built from the actual numbers. It's FastAPI, SQLAlchemy and scikit-learn on the back end, Next.js and TypeScript on the front end, with 94 backend and 11 frontend tests."

### 2-minute walkthrough

1. **Data (20 s).** On the Data Management page I validate the deliberately broken CSV, `data/sample_sales_invalid.csv`. The report shows 11 rows: 4 accepted, 6 rejected with line numbers and reasons, and 1 exact duplicate excluded. Nothing is stored until I click Import. Loading the sample goes through the same pipeline.
2. **Forecast (40 s).** I pick SKU-1006, a strong weekday pattern, and a 30-day horizon. The table shows the holdout from June 3 to June 30 for all three models. The random forest's MAE is 3.90 against the baseline's 10.43, and the holdout chart shows why: the baseline is flat while the forest follows the weekday pattern. Then I show SKU-1008, which has only 40 days of history. It's labelled low confidence and shows no metrics, because I won't report numbers I can't validate.
3. **Inventory (40 s).** SKU-1001 is critical. Lead-time demand is 422 and safety stock is 214, so the reorder point is 636. Stock is 250, so we reorder up to a target of 1,238. The raw gap is 988, which the MOQ and pack size of 24 round up to 1,008. Stock runs out in 5.7 days, before the 10-day lead time ends, which is why it's critical rather than just high. I then edit a product's stock live to show the recommendation updating.
4. **Engineering (20 s).** The ML and inventory maths are pure functions with unit tests. Routes are thin, errors are structured, and the schema is managed with Alembic. I also explain one real bug: the forecast boundary bug, which I found from the dashboard chart and fixed with regression tests.

---

## Part B: Mandatory topics

### 1. Why compare a baseline model with a candidate model?

**Simple:** a baseline tells you whether the complex model is actually adding value. If a 28-day average does just as well, the complex model is just extra risk.

**Detail:** model selection needs a reference point. Without one, an MAE of 4 means nothing. The baseline is cheap, robust and hard to overfit. The candidate has to beat it on the same unseen dates, and ties go to the simpler model.

In our sample run the baseline won on SKU-1002, 1004 and 1005 (trend, intermittent and declining demand). The random forest won clearly only where weekly structure exists: SKU-1001 by 37% and SKU-1006 by 63%.

**In the code:** `MovingAverageModel`, `SeasonalNaiveModel`, `RandomForestModel` and `select_model` in `backend/app/ml/forecasting.py`; the `MODEL_COMPLEXITY_ORDER` tie-break; `test_select_model_prefers_lowest_mae_and_simpler_on_ties`.

### 2. Why use chronological train/test splitting?

**Simple:** in real life you forecast the future from the past. A random split lets the model train on days *after* the test days, which is cheating.

**Detail:** time-series rows are autocorrelated. With a random split, a test day sits between training days, and the model can effectively interpolate its neighbours. That makes the metrics look much better than real forecasting performance.

We hold out the **last** `clip(n/5, 14, 28)` days, fit only on earlier data, and forecast the whole holdout in one multi-step pass, exactly as in production.

**In the code:** `holdout_size` and `evaluate_models`; `test_evaluation_is_chronological_and_uses_same_dates_for_all_models`.

### 3. What are MAE and RMSE?

**Simple:** MAE is the average size of the error, in units. RMSE is similar, but it squares errors first, so big misses count more.

**Detail:**

- MAE = mean(|y − ŷ|).
- RMSE = sqrt(mean((y − ŷ)²)).
- Both are in units of demand per day. RMSE ≥ MAE always holds, and a big gap between them means occasional large errors.

We select on MAE because stock cost is roughly linear in the error, and MAE is less dominated by promotion spikes. Both metrics are stored per model per run.

For example, SKU-1003's random forest had a slightly better MAE (3.41 vs 3.43) but a worse RMSE (4.43 vs 4.39). That means similar average error with a few larger misses. The app flags the gain as small.

**In the code:** `backend/app/ml/metrics.py`; `test_mae_and_rmse_known_values`.

### 4. How do lead-time demand and safety stock determine the reorder point?

**Simple:** the reorder point is how much stock you need to survive until a new delivery arrives, plus a cushion. So reorder point = demand during the lead time + safety stock.

**Detail:**

- Lead-time demand is the **sum of the daily forecast** over the next L days, not average × L, so uneven forecasts are respected.
- Safety stock is either a fixed quantity or average forecast demand × safety days.
- When stock is at or below the reorder point, an order must be placed now.

Days-based safety stock is a heuristic. It is not a service-level guarantee, because we have no forecast-error distribution in the formula. That is a future improvement.

Example (SKU-1001): 422 + 214 = 636.

**In the code:** `recommend()` in `backend/app/services/inventory_policy.py`; `test_reorder_point_is_lead_time_demand_plus_safety_stock`.

### 5. How is reorder quantity calculated?

**Simple:** order enough to reach a target level that covers the lead time plus a coverage period, plus safety stock. Then round to the supplier's minimum and pack size.

**Detail:**

- Target stock = forecast over (L + coverage days) + safety stock.
- Gap = max(0, target − stock).
- We order only if stock ≤ reorder point. This is an (s, S) policy, which avoids tiny top-up orders.
- The gap is raised to the MOQ, then rounded **up** to whole packs, so the result is never below the MOQ and never undershoots the target.
- The reorder point and the target are deliberately different numbers. A test asserts they differ.

Example (SKU-1001): target 1,238 − stock 250 = 988. Raised to the MOQ of 100 (no change) and rounded up to packs of 24, that gives 1,008.

**In the code:** `apply_order_constraints`; `test_minimum_order_quantity_and_pack_rounding`.

### 6. How are invalid CSV datasets detected?

**Simple:** two layers. File-level problems reject the whole upload. Row-level problems reject individual rows with reasons. Nothing invalid is ever silently fixed.

**Detail:**

- **File level:**
  - wrong extension or content type → 415
  - more than 5 MB or 200,000 rows → 413
  - empty, binary, non-UTF-8 or malformed (pandas `ParserError`) → 422
  - missing or ambiguous required columns → 422
- **Row level** (vectorised pandas masks):
  - dates must parse as `%Y-%m-%d` and not be in the future
  - quantities must be finite and ≥ 0
  - product IDs must match a safe pattern
- The report gives counts per issue, up to 50 rejected rows with line numbers and reasons, and correction instructions.

**In the code:** `validate_sales_csv`, `decode_upload`, `parse_csv` and `map_columns` in `backend/app/services/csv_validation.py`; 18 tests in `tests/test_csv_validation.py`.

### 7. How does the system prevent misleading forecasts?

**Simple:** it never shows numbers it can't back up. Metrics come only from a real holdout. Short histories are labelled low confidence. Every assumption is stated as a warning.

**Detail:**

- **Minimum history:** under 14 days we refuse to forecast; under 56 days, metrics are `null` and the forecast is marked `confidence: "low"`.
- **No training metrics:** training-set accuracy is never reported.
- **Same test dates:** every model is scored on the same holdout.
- **Warnings:** shown when more than 10% of days were zero-filled, and when the horizon is longer than the validated holdout.
- **Limitations:** listed on every run (no intervals, a single window, censored demand).
- **No fake data:** the frontend never substitutes fake numbers if the API fails.

**In the code:** `forecast_product`, `BASE_LIMITATIONS`, `MIN_EVALUATION_HISTORY_DAYS`; `test_short_history_is_low_confidence_without_metrics`; `api.test.ts` ("reports an unreachable backend instead of returning fake data").

---

## Part C: Technical questions

1. **Walk me through the architecture.**
   - A Next.js client calls FastAPI through a typed client (`src/lib/api.ts`).
   - Routes stay thin. The logic lives in services, and the ML and inventory code is pure Python. SQLAlchemy runs over SQLite, with Alembic migrations.
   - See `docs/ARCHITECTURE.md`.
2. **Why FastAPI?**
   - Pydantic validation (for example `ForecastRequest.horizon_days` with `ge=1, le=90`) and automatic OpenAPI docs at `/docs`.
   - Dependency injection (`get_db`), which tests override.
3. **What makes the API RESTful?**
   - Resource-oriented paths and correct verbs: POST creates (201), PUT replaces settings, GET is side-effect free.
   - Proper status codes (404, 409, 413, 415, 422) and versioning under `/api/v1`.
   - Actions that are not pure CRUD are modelled as sub-resources: `/datasets/{id}/activate`, `/forecasts/batch`.
4. **How are errors structured?**
   - `AppError` subclasses plus handlers in `app/errors.py` produce `{"error": {code, message, details, request_id}}`.
   - A test forces a 500 and asserts that no internal message or traceback leaks (`test_errors_never_leak_stack_traces`).
5. **What does logging capture?**
   - Middleware logs method, path, status, duration and request ID. Services log summary counts.
   - Uploaded data is never logged.
   - The request ID returned in errors lets you match a user report to the log line.
6. **Describe the database schema.**
   - Seven tables (README §6).
   - Key constraints: unique `products.product_id`, unique `datasets.file_sha256`, unique (dataset, product, date) for sales, unique (run, date) for points.
7. **How do you handle transactions?**
   - Each mutating service commits once and calls `rollback()` on any exception.
   - `commit_dataset` writes products, the dataset and all records atomically.
   - `test_failed_commit_rolls_back` simulates a failing bulk insert and asserts nothing was stored.
8. **What happens if I upload the same file twice?**
   - A SHA-256 check returns `409 duplicate_import` with the existing dataset ID, and the UI offers to activate it.
   - A *modified* file creates a new version and becomes active.
9. **How are duplicate transactions handled?**
   - Exact duplicate rows (every mapped column equal) are excluded by default, keeping the first, and listed by line number.
   - Non-identical rows for the same product and date are summed into a daily total (`aggregated_rows`), not discarded.
   - Because there is no transaction ID, identical rows are ambiguous, so `duplicate_policy=keep` exists.
10. **How are missing dates handled?**
    - Validation reports them per product, up to the dataset end.
    - Forecasting fills them with zero, assuming transaction exports omit days without sales, and warns if more than 10% of days are filled.
    - The zero-fill is not applied to the stored data.
11. **What is data leakage, and how did you prevent it?**
    - Leakage means information from the evaluation period reaches training or the features.
    - Prevented by: a chronological split; fitting only on the training window; `lag_features` reading only `values[:t]`; and the holdout predicted recursively without actual values.
    - Tests: `test_lag_features_do_not_use_future_values` and `test_baseline_evaluation_ignores_holdout_values`.
12. **How do you limit overfitting?**
    - Shallow trees (depth 8, min leaf 3) and few features.
    - No hyperparameter tuning on the holdout.
    - The model must beat the baseline on unseen data, and ties go to the simpler model.
13. **Why recursive multi-step forecasting?**
    - The lag-1 feature is unknown beyond tomorrow, so each prediction becomes the next step's lag.
    - Alternative: a direct model per horizon. It avoids error accumulation but costs one model per step.
    - Errors compound over long horizons, so the forecast warns when the horizon is longer than the holdout.
14. **How is stockout risk classified?**
    - Rules are evaluated in order:
      - **critical:** stock = 0, or the stockout comes before the lead time ends
      - **high:** stock ≤ reorder point
      - **moderate:** within 7 days of demand of the reorder point
      - **low:** otherwise
    - Days to stockout walks the daily forecast cumulatively, so a spike on day 3 is handled correctly (`test_variable_demand_stockout_walks_daily_forecast`).
15. **How is overstock detected?**
    - It is relative to demand: days of cover (stock ÷ average forecast demand) greater than the threshold (default 90), or stock held with zero forecast demand.
    - 1,000 units is overstock at 10 per day but not at 100 per day (`test_overstock_uses_coverage_relative_to_demand`).
16. **How is the upload secured?**
    - Extension, content-type and binary checks.
    - A bounded read (`_read_limited` reads at most limit + 1 bytes).
    - Strict UTF-8 decoding and a row cap.
    - Data is parsed as strings and never executed. Nothing is written to disk.
    - ORM queries are parameterised (no SQL string building), and CORS is limited to local origins.
17. **What tests did you write?**
    - Backend (94): validation, forecasting, inventory, API, persistence and migration tests.
    - Frontend (11): the API client, the form and the report view.
    - Plus ESLint, `tsc` and `next build`. See `docs/TESTING.md`.
18. **How is the work reproducible?**
    - Seed 42 for the sample, enforced by a test that compares against the committed CSV.
    - `random_state=42` with `n_jobs=1` for the forest, enforced by a test.
    - Pinned Python dependencies and an npm lockfile; migrations create the schema.
19. **SQLite or PostgreSQL?**
    - SQLite: zero setup, a single file, good for a local demo. But writes are serialised, and it has limited concurrency and types (we had to re-attach UTC to timestamps).
    - PostgreSQL in production: concurrent writes, real `timestamptz`, JSONB for reports, and partitioning of sales by dataset.
    - The SQLAlchemy models are portable. Only `DATABASE_URL` and a migration review change.
20. **Why synthetic data, and what are its risks?**
    - It is reproducible and shareable, it has no privacy issues, and it covers known patterns (weekly, trend, annual, intermittent, promotions, short history), so I can check that models behave as expected.
    - The risk: real data has censoring, outliers and regime changes. Good scores on synthetic data do not prove real-world accuracy, and the UI labels the dataset as synthetic.
21. **How would you take this to production?**
    - Rolling-origin backtesting.
    - Prediction intervals with service-level safety stock (z × σ × √L).
    - A background job queue for batch forecasts.
    - PostgreSQL, authentication and multi-tenancy.
    - Recommendation history and audit.
    - Handling promotions, holidays and stockout-censored demand.
    - Monitoring of forecast error against actual sales.
    - Docker and CI.
    - Playwright end-to-end tests.

## Part D: Scenario-based debugging questions

1. **"A product's forecast starts on a date that's already in history." What happened?**
   - This really happened here.
   - The series ended at the product's last sale, not the dataset end, so intermittent SKU-1004 lost its trailing zero days. Found from the dashboard chart, then traced to `demand_series` in the API.
   - Fixed by passing `end_date` to `build_daily_series`. Regression tests were added. See `DEVELOPMENT_WORKFLOW.md` #2.
2. **"Upload of a file where every date is invalid returns a 500."**
   - Also real.
   - `.dt.date` on an all-`NaT` series keeps the datetime dtype, so comparing it with a `date` raises. The fix compares against `pd.Timestamp(today)`.
   - The tests caught it because the test cases deliberately included an all-invalid file.
3. **"The dashboard says 0 products at risk, but stock is clearly low."**
   - Check whether the product has inventory settings (`status: not_configured`) or a forecast (`no_forecast`). Products without both aren't classified, and the dashboard shows a warning banner about them.
   - Then check whether the latest forecast belongs to the *active* dataset.
4. **"The random forest has great MAE in my notebook but loses in the app."**
   - Ask how the notebook was evaluated. A random split, or using actual holdout lags (one-step-ahead) instead of recursive multi-step, inflates accuracy.
   - The app evaluates multi-step and recursive, the way it is actually used.
5. **"The recommended order is 216 but the gap was only 110."**
   - The MOQ is 200, which is raised to whole packs of 24, giving 216. The explanation line "Adjusted to … to respect the minimum order and pack size" shows this.
   - Test: `test_minimum_order_quantity_and_pack_rounding`.
6. **"The frontend shows 'Cannot reach the StockWise API'."**
   - The backend isn't running, `NEXT_PUBLIC_API_BASE_URL` is wrong (it is baked in at build time, so restart the dev server), or CORS is blocking an unexpected origin.
   - Check the browser network tab and the `CORS_ORIGINS` setting.
7. **"Timestamps show 5½ hours off."**
   - SQLite drops tzinfo, so naive UTC values are read as local time.
   - Fixed with the `UTCDateTime` decorator, which makes the API emit `Z`.

## Part E: ML evaluation and forecasting questions

1. **Why is the holdout 28 days, and not the forecast horizon?**
   - It is bounded to between 14 and 28 days, but always at least 42 training days are kept.
   - The holdout is fixed and the same for all models, so comparisons are fair. A horizon-dependent holdout would make runs incomparable.
   - When the horizon is longer than the holdout, the forecast warns that the extra days are not directly validated.
2. **Why not MAPE?**
   - Intermittent products have zero-demand days, so MAPE divides by zero or explodes.
   - MAE and RMSE are scale-dependent but well-defined.
   - For cross-product comparison, MASE (MAE scaled by the naive forecast's MAE) would be a good addition.
3. **Is one 28-day holdout enough to choose a model?**
   - It is a weak signal for small differences. SKU-1003's 0.6% gain is noise-level, and the app says so.
   - The improvement would be rolling-origin cross-validation (several cut-offs) and averaging the errors.
4. **How do you handle intermittent demand?**
   - Currently the baseline wins (SKU-1004, MAE 0.49).
   - A specialised method such as Croston/SBA would be a candidate. For inventory, a stockout-probability approach is better than mean demand.
5. **What does "low confidence" mean exactly?**
   - Between 14 and 55 days of history, so no holdout evaluation is possible.
   - We return a moving average of the available history, label it, report no metrics, and say how many more days are needed: 56 − n.
   - Recommendations based on such a forecast carry a warning.
6. **Why refit on the full history after selection?**
   - The holdout was used only to *choose* the model. The most recent data is the most informative for the future, so the final model trains on everything.
   - The reported metric is therefore an estimate for a slightly smaller training set, which is standard practice.
7. **How do you ensure the random forest isn't using "tomorrow's" data?**
   - Every feature is built by `lag_features(values, t, date)`, which only slices `values[:t]`.
   - Training rows are built with the same function, so training and serving use identical features.
   - Two tests check this directly.

## Part F: Implemented vs future

| Implemented | Future |
|---|---|
| CSV validation with preview, versioned datasets, duplicate policy | Netting returns; mapping custom columns in the UI |
| 3 models, chronological holdout, MAE/RMSE, documented selection | Rolling-origin backtest, ETS/Croston, prediction intervals, a global model |
| (s, S) heuristic with MOQ and pack size, risk and overstock rules, explanations | Service-level safety stock, supplier calendars, budget constraints, optimisation |
| SQLite + Alembic, structured errors, logging, 105 automated tests | PostgreSQL, authentication, a job queue, Docker, CI, end-to-end tests, monitoring |
| Recommendations computed on request | Persisted recommendation history |

## Final revision checklist

- [ ] I can state the MAE and RMSE formulas and when each is the better guide.
- [ ] I can explain why the split is chronological, with an example of how random splits leak.
- [ ] I can compute the reorder point and order quantity for SKU-1001 from memory: 422 + 214 = 636; 1,238 − 250 = 988, rounded to 1,008.
- [ ] I can explain the (s, S) choice and how the reorder point differs from the target stock.
- [ ] I can list the risk rules in order, and the overstock rule.
- [ ] I can explain the duplicate and aggregation policy and the missing-date assumption.
- [ ] I can describe the insufficient-history thresholds (14 and 56 days) and why they exist.
- [ ] I can explain bug #1 and bug #2 end to end (symptom → root cause → fix → test).
- [ ] I know where every module lives (`ml/forecasting.py`, `services/inventory_policy.py`, `services/csv_validation.py`).
- [ ] I can explain SQLite vs PostgreSQL trade-offs and three production improvements.
- [ ] I am honest about which tools I used (Claude Code, and CodeZero only for the tasks I actually did).
- [ ] I have run the demo end to end at least once on a fresh `seed --reset`.
