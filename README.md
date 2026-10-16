# StockWise AI

**Demand forecasting and explainable inventory recommendations.** A full-stack app built for the Edvexa Software Engineer Intern assignment.

You upload historical sales as CSV. StockWise AI validates the data and stores it as a versioned dataset. For each product it compares a baseline forecasting model with two candidate models on a chronological holdout, then forecasts demand with the model that scored best. It also turns those forecasts into reorder recommendations, each with an explanation.

Everything shown in the UI is computed from the data: there are no hardcoded metrics, and no fake fallback data when the backend is unreachable.

> The bundled sample dataset is **synthetic**. It is generated deterministically with seed 42 by `backend/app/services/sample_data.py`.

---

## 1. Project overview

| Layer | Responsibility |
|---|---|
| **Frontend** (Next.js 15, TypeScript, Tailwind, Recharts) | Five pages (Overview, Demand Forecasting, Inventory, Data Management, Insights). Uses a typed API client, loading/empty/error states, and forms validated with React Hook Form + Zod |
| **Backend** (FastAPI, Pydantic v2, SQLAlchemy 2, Alembic) | Versioned REST API under `/api/v1`, structured errors, request logging, upload limits |
| **ML** (pandas, NumPy, scikit-learn) | Daily series preparation, three forecasting models, chronological holdout evaluation, model selection |
| **Inventory policy** (pure Python) | Lead-time demand, safety stock, reorder point, target stock, order constraints, stockout and overstock rules |
| **Database** (SQLite) | Products, dataset versions, daily sales, forecast runs and points, model evaluations, inventory settings |

## 2. Features

- CSV upload with a **dry-run validation and preview** (`/datasets/validate`) before committing (`/datasets/upload`).
- Validation report that covers:
  - required columns and header aliases
  - dates in ISO format only, with future dates rejected
  - finite, non-negative quantities
  - product IDs
  - missing values and exact duplicates
  - aggregation of same-day transactions
  - missing calendar dates
  - file-size and row-count limits
  - malformed, empty, binary and non-CSV files
  - rejected rows listed by line number with reasons, plus correction instructions
- A downloadable synthetic sample CSV and a one-click "Load sample dataset" button. Both are served by the backend.
- Product-level forecasts with a horizon of 1–90 days (the UI offers 7, 14, 30, 60 and 90).
- A **baseline** (28-day moving average) compared with two **candidates** (weekly seasonal-naive and a random forest on lag features). All three are evaluated on the same chronological holdout with **MAE and RMSE**, and the lowest MAE wins (ties go to the simpler model).
- Honest handling of insufficient history:
  - fewer than 14 days: the forecast is refused
  - 14–55 days: a low-confidence fallback with no metrics
- Inventory settings per product:
  - stock and lead time
  - safety stock, as either days of demand or a fixed quantity
  - MOQ and pack size
  - coverage days and overstock threshold
- Reorder recommendations showing reorder point, target stock, order quantity, days until stockout, risk level (critical/high/moderate/low), an overstock flag and a plain-language explanation generated from the numbers.
- Dashboard KPIs, a combined history + forecast chart, a risk distribution, recent datasets and forecast runs, and data-quality warnings.
- Insights: demand trends (recent vs prior window), monthly demand by category, top forecast demand, reorder priorities and potential overstock.
- Persistent forecast history, plus dataset versioning with activation of earlier versions.

## 3. Architecture

```
Browser (Next.js app, :3000)
   │  fetch() via src/lib/api.ts  (NEXT_PUBLIC_API_BASE_URL)
   ▼
FastAPI (:8000)  app/main.py — CORS, request-id + logging middleware, error handlers
   ├── app/api/routes/*        thin HTTP layer (validation, status codes)
   ├── app/services/*          business logic + persistence (transactions, rollback)
   │     csv_validation.py     pure CSV parsing/validation
   │     inventory_policy.py   pure reorder math
   │     datasets / products / forecasts / inventory / analytics  (DB orchestration)
   ├── app/ml/forecasting.py   pure forecasting engine; app/ml/metrics.py MAE/RMSE
   └── app/db/models.py        SQLAlchemy ORM  →  SQLite (Alembic migrations)
```

There is more detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 4. Technology choices

- **FastAPI + Pydantic**: request validation and OpenAPI docs come for free, and the type hints are easy to test.
- **SQLite + SQLAlchemy + Alembic**: no setup locally. The ORM keeps a move to PostgreSQL to a configuration change plus a migration review.
- **pandas / NumPy / scikit-learn**: the standard tools for time-series preparation. `RandomForestRegressor` handles non-linear weekday and level effects without feature scaling, and it is deterministic when `random_state` is fixed.
- **Next.js + TypeScript + Tailwind + Recharts**: typed UI, responsive layout, accessible charts.
- **No paid APIs, cloud services or credentials.**

## 5. Directory structure

```
stockwise-ai/
├── backend/
│   ├── app/
│   │   ├── api/routes/        health, products, datasets, forecasts, inventory, dashboard
│   │   ├── db/                models.py, session.py, migrate.py
│   │   ├── ml/                forecasting.py, metrics.py
│   │   ├── services/          csv_validation, datasets, products, forecasts,
│   │   │                      inventory, inventory_policy, analytics, sample_data
│   │   ├── config.py  errors.py  logging_config.py  schemas.py  main.py
│   ├── alembic/ (env.py, versions/0001_initial_schema.py)   alembic.ini
│   ├── scripts/               init_db.py, seed.py, generate_sample_csv.py
│   ├── tests/                 5 test modules (+ conftest), 94 tests
│   ├── requirements.txt  requirements-dev.txt  pytest.ini
├── frontend/
│   ├── src/app/               page.tsx (overview), forecasting/, inventory/, data/, insights/
│   ├── src/components/        ui/, charts/, layout/, InventoryForm, ValidationReportView (+ tests)
│   ├── src/lib/               api.ts (typed client), types.ts, format.ts, useApi.ts
│   └── package.json  vitest.config.mts  eslint.config.mjs  tailwind.config.ts
├── data/                      sample_sales.csv (synthetic), sample_sales_invalid.csv (demo)
├── docs/                      architecture, API, model selection, testing, workflow, interview prep…
├── screenshots/               agent-verification/ (captured during development) + manual checklist
├── .env.example  .gitignore  README.md
```

## 6. Database schema

| Table | Key columns | Constraints / indexes |
|---|---|---|
| `products` | `id` PK, `product_id` (natural key), `name`, `category`, `unit_price`, timestamps | `product_id` unique, index on `category` |
| `datasets` | `id` PK, `filename`, `file_sha256`, `is_active`, `is_synthetic`, row counts, `date_start/end`, `duplicate_policy`, `validation_report` (JSON), `created_at` | `file_sha256` unique (prevents re-importing the same file) |
| `sales_records` | `dataset_id` FK, `product_fk` FK, `date`, `quantity`, `transaction_count` | unique (`dataset_id`, `product_fk`, `date`), index (`product_fk`, `date`) |
| `forecast_runs` | `product_fk` FK, `dataset_id` FK, `horizon_days`, `selected_model`, `selection_reason`, `confidence`, history/forecast dates, `total_forecast`, `warnings`, `limitations`, `created_at` | index (`product_fk`, `created_at`) |
| `forecast_points` | `run_id` FK, `date`, `predicted_quantity` | unique (`run_id`, `date`) |
| `model_evaluations` | `run_id` FK, `model_name`, `role`, `is_selected`, `evaluated`, `mae`, `rmse`, `test_samples`, train/test dates, `holdout` JSON (date, actual, predicted), `warnings` | unique (`run_id`, `model_name`) |
| `inventory_settings` | `product_fk` FK (unique), `current_stock`, `supplier_lead_time_days`, `safety_stock_days` / `safety_stock_quantity`, `minimum_order_quantity`, `order_pack_size`, `coverage_days`, `overstock_threshold_days`, timestamps | one row per product |

**Versioning policy:** every committed upload creates a new, immutable dataset version and becomes the **active** one. Forecasts, products and dashboards read the active dataset, and `POST /datasets/{id}/activate` switches back to an earlier version. A byte-identical re-upload is rejected with `409 duplicate_import`. Recommendation history is **not** stored: recommendations are recomputed from the latest stored forecast and the current settings.

## 7. CSV schema and sample data

| Column | Required | Rules | Accepted header aliases |
|---|---|---|---|
| `date` | yes | `YYYY-MM-DD`, not in the future | date, sale_date, sales_date, order_date, transaction_date |
| `product_id` | yes | 1–64 chars: letters, digits, `-`, `_`, `.` | product_id, productid, sku, product_code, item_id |
| `quantity` | yes | finite number ≥ 0 | quantity, qty, quantity_sold, units_sold, units, sales_quantity |
| `product_name` | no | text | product_name, item_name |
| `category` | no | text | category, product_category |
| `unit_price` | no | number ≥ 0 (invalid → left empty + warning) | unit_price, price, price_per_unit |

Headers are normalised (case, spaces, punctuation), so `Product ID` and `Quantity Sold` work. If two columns map to the same field, the upload is rejected as ambiguous: the app never guesses which one you meant.

`data/sample_sales.csv` is **synthetic**: 8 products, 2024-01-01 → 2025-06-30, 4,106 rows. The demand patterns are:

| Product | Pattern |
|---|---|
| SKU-1001 | weekly seasonality |
| SKU-1002 | upward trend |
| SKU-1003 | annual seasonality |
| SKU-1004 | intermittent demand |
| SKU-1005 | downward trend |
| SKU-1006 | strong weekday pattern |
| SKU-1007 | promotion spikes |
| SKU-1008 | only 40 days of history |

About 15% of larger sales days are split into two transactions to exercise same-day aggregation. To regenerate the file:

```bash
python -m scripts.generate_sample_csv
```

A test checks that the generated file is identical to the committed one. `data/sample_sales_invalid.csv` is a small file with deliberate errors, used for the demo.

## 8. Data validation and duplicate policy

- **File level** (request rejected):
  - not `.csv` or unsupported content type → `415`
  - more than 5 MB or more than 200,000 rows → `413`
  - empty, malformed, not UTF-8, missing required columns or ambiguous columns → `422`
- **Row level** (row rejected and listed with reasons):
  - missing or invalid date
  - future date
  - missing or invalid `product_id`
  - missing, non-numeric, infinite or negative quantity

  Invalid values are **never replaced**.
- **Exact duplicates** (every mapped column identical) are excluded by default (`duplicate_policy=exclude`) and the first occurrence is kept. Use `duplicate_policy=keep` when identical rows are genuine separate transactions.
- **Different rows for the same product and date** are legitimate separate transactions. They are **summed** into a daily total, never discarded.
- **Missing calendar dates** are reported per product. Coverage runs from the product's first sale to the dataset end date.
- If no row passes validation, nothing is stored (`422 no_valid_rows`).

## 9. Forecasting pipeline

Implemented in `backend/app/ml/forecasting.py`:

1. **Build the daily series.** `build_daily_series` aggregates sales by date and reindexes to a continuous daily calendar, from the product's first sale to the **dataset's last date**.
2. **Treat missing dates as zero.** A day with no records is set to 0. *Assumption:* transaction exports only contain days with sales.
   - When more than 10% of days are filled this way, the forecast carries a warning, because a data outage looks the same as zero demand.
3. **Apply the history policy:**
   - fewer than **14 days** → `422 insufficient_history`, and no forecast is produced
   - **14–55 days** → moving-average fallback, labelled `confidence: "low"`, with no metrics and a message saying how many more days are needed
   - **56 days or more** → chronological holdout evaluation (below), then the selected model is refitted on the full history
4. **Clip negative predictions** to 0. This is defensive only: none of the models can produce negative values from non-negative history.

## 10. Baseline and candidate models

| Model | Role | Definition |
|---|---|---|
| `moving_average` | baseline | Flat forecast = mean of the last 28 days of the training window |
| `seasonal_naive` | candidate | Repeats the last observed 7-day cycle |
| `random_forest` | candidate | `RandomForestRegressor` (100 trees, depth 8, min leaf 3, `random_state=42`) |

The random forest's features are lags 1/7/14/28, trailing 7-day and 28-day means, the trailing 7-day standard deviation, day of week and a weekend flag. All of them are computed **only from values before the target day** by one function, `lag_features`, which is shared by training and prediction.

Multi-step forecasts are **recursive**: each prediction is fed into the features for the next day.

## 11. Chronological evaluation methodology

- The holdout is the **last** `clip(n/5, 14, 28)` days. There is no random split.
- Every model is fitted on the training window only, then forecasts the whole holdout in one multi-step pass, so it never sees holdout actual values.
- All models are scored on **exactly the same dates**. Training-set metrics are never reported.
- Selection: lowest holdout MAE. Ties go to the simpler model, in the order baseline < seasonal naive < random forest. The selection reason states the MAE gain over the baseline, and flags gains under 5% as small.
- Every forecast run stores, per model: train period, test period, sample count, MAE, RMSE and the holdout points.
- If the horizon is longer than the holdout, the forecast warns that days beyond the holdout length are not directly validated.

Actual results on the synthetic sample, holdout 2025-06-03 → 2025-06-30 (MAE / RMSE, units per day):

| Product | Moving average | Seasonal naive | Random forest | Selected |
|---|---|---|---|---|
| SKU-1001 | 6.57 / 8.62 | 6.00 / 6.92 | 4.13 / 5.08 | random_forest |
| SKU-1002 | 4.62 / 5.88 | 5.43 / 6.57 | 5.01 / 6.64 | moving_average |
| SKU-1003 | 3.43 / 4.39 | 3.68 / 4.52 | 3.41 / 4.43 | random_forest (gain < 1%, flagged as small) |
| SKU-1004 | 0.49 / 0.67 | 0.82 / 1.09 | 0.55 / 0.69 | moving_average |
| SKU-1005 | 2.43 / 2.85 | 3.43 / 4.10 | 2.54 / 3.19 | moving_average |
| SKU-1006 | 10.43 / 12.32 | 6.64 / 8.84 | 3.90 / 5.22 | random_forest |
| SKU-1007 | 2.63 / 3.94 | 2.18 / 3.63 | 2.55 / 3.92 | seasonal_naive |
| SKU-1008 | — | — | — | moving_average (low confidence, 40 days) |

The baseline wins on 3 of the 7 evaluated products. A more complex model is **not** automatically better. More detail is in [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md).

## 12. MAE and RMSE

$$\text{MAE}=\frac1n\sum_{t=1}^{n}|y_t-\hat y_t| \qquad \text{RMSE}=\sqrt{\frac1n\sum_{t=1}^{n}(y_t-\hat y_t)^2}$$

- **MAE** is the average size of the error.
- **RMSE** squares the errors before averaging, so it penalises large misses more. RMSE ≥ MAE always holds.
- Both are in **units of demand per day**.

They are implemented in `backend/app/ml/metrics.py` and tested against hand-computed values.

## 13. Inventory formulas and assumptions

Implemented in `backend/app/services/inventory_policy.py`. Let *f* be the daily forecast and *L* the supplier lead time in days.

| Quantity | Formula |
|---|---|
| Lead-time demand | Σ f over days 1…L |
| Safety stock | fixed quantity, **or** mean(f) × safety-stock days |
| Reorder point | lead-time demand + safety stock |
| Protection period | L + coverage days |
| Target stock | Σ f over the protection period + safety stock |
| Order-up-to gap | max(0, target stock − current stock) |
| Recommended quantity | if current stock ≤ reorder point: the gap, raised to the MOQ, then rounded **up** to whole packs; otherwise 0 |
| Days until stockout | first fractional day on which cumulative forecast demand exceeds stock (walks the daily forecast, so uneven demand is handled); none if stock is not exhausted within the horizon |

Risk rules, checked in order:

| Risk | Rule |
|---|---|
| **critical** | demand > 0 and either stock = 0 or stockout comes before the lead time ends |
| **high** | stock ≤ reorder point |
| **moderate** | stock ≤ reorder point + 7 days of average demand |
| **low** | anything else, including zero demand |

**Overstock:** stock covers more days of average forecast demand than the threshold (default 90), **or** stock is held while forecast demand is zero. A high absolute stock level alone does not trigger it.

If the forecast horizon is shorter than the protection period, the extra days use the average daily forecast and the recommendation carries a warning.

This is an **explainable, configurable heuristic**. It is a forecast-driven (s, S) policy, *not* a constrained optimisation. Safety stock by "days" is a heuristic and does not guarantee a statistical service level.

## 14. API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + DB check |
| GET | `/api/v1/products` | Products in the active dataset (`search`, `category`, `include_inactive`, `limit`, `offset`) |
| GET | `/api/v1/products/categories` | Distinct categories |
| GET | `/api/v1/products/{product_id}` | Details + zero-filled daily sales (`start_date`, `end_date`) |
| POST | `/api/v1/datasets/validate` | Dry-run validation + preview (multipart `file`, `duplicate_policy`) |
| POST | `/api/v1/datasets/upload` | Validate and commit a new active dataset (201) |
| GET | `/api/v1/datasets/sample` | Download the synthetic sample CSV |
| POST | `/api/v1/datasets/sample/load` | Import the sample through the same pipeline (201) |
| GET | `/api/v1/datasets` | Dataset versions (paginated) |
| GET | `/api/v1/datasets/{dataset_id}` | Dataset + full validation report |
| POST | `/api/v1/datasets/{dataset_id}/activate` | Make a version active |
| POST | `/api/v1/forecasts` | Evaluate, select and forecast one product (201) |
| POST | `/api/v1/forecasts/batch` | Forecast all (or the listed) products (201) |
| GET | `/api/v1/forecasts` | Forecast runs (`product_id`, `dataset_id`, paginated) |
| GET | `/api/v1/forecasts/{forecast_id}` | Run with points and evaluations |
| GET | `/api/v1/inventory` | All inventory settings |
| POST | `/api/v1/inventory` | Create settings (201; 409 if they exist) |
| PUT | `/api/v1/inventory/{product_id}` | Replace settings (404 if none) |
| GET | `/api/v1/inventory/recommendations` | Recommendations (`risk`, `reorder_only`) |
| GET | `/api/v1/dashboard/summary` | KPIs and series (`period_days`, `history_days`, `category`) |
| GET | `/api/v1/insights` | Trends and priorities (`window_days`) |

Interactive docs are served at <http://localhost:8000/docs> while the backend runs. Examples are in [docs/API.md](docs/API.md).

## 15. Example requests

```bash
curl -X POST localhost:8000/api/v1/datasets/upload -F "file=@data/sample_sales.csv;type=text/csv"
```

```bash
curl -X POST localhost:8000/api/v1/forecasts -H "Content-Type: application/json" -d "{\"product_id\":\"SKU-1001\",\"horizon_days\":30}"
```

```bash
curl -X PUT localhost:8000/api/v1/inventory/SKU-1001 -H "Content-Type: application/json" -d "{\"current_stock\":250,\"supplier_lead_time_days\":10,\"safety_stock_days\":5}"
```

```bash
curl "localhost:8000/api/v1/inventory/recommendations?risk=critical"
```

Every error response has the same shape:

```json
{"error": {"code": "not_found", "message": "Product 'NOPE' was not found.", "details": null, "request_id": "c8a97399977d"}}
```

## 16. Installation

Prerequisites: **Python 3.11+**, **Node.js 18.18+** (developed with 22.19) and npm. Commands below are run from the repository root unless a step says otherwise.

Install the backend:

```bash
cd backend
```

```bash
python -m venv .venv
```

Activate the virtual environment. On Windows (PowerShell):

```bash
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements-dev.txt
```

Install the frontend:

```bash
cd frontend
```

```bash
npm install
```

## 17. Environment variables

Copy `.env.example` to `.env` (backend) and `frontend/.env.local` (frontend) if you need to change the defaults. Everything works without them.

| Variable | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<repo>/backend/stockwise.db` | backend |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | backend |
| `LOG_LEVEL` | `INFO` | backend |
| `MAX_UPLOAD_BYTES` / `MAX_UPLOAD_ROWS` | `5242880` / `200000` | backend |
| `AUTO_MIGRATE` | `true` (run Alembic on startup) | backend |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | frontend |

## 18. Database initialization

From `backend/`, with the virtual environment active:

```bash
python -m scripts.init_db
```

This runs `alembic upgrade head`. Add `--reset` to delete the SQLite file first. The API also migrates automatically on startup.

## 19. Sample-data loading

From `backend/`. This imports the synthetic sample, applies demo inventory settings and creates 60-day forecasts:

```bash
python -m scripts.seed --reset
```

Alternatively, in the UI: **Data Management → Load sample dataset**, then **Generate forecasts for all products**. The demo inventory values in `scripts/seed.py` are configuration. Every forecast, metric and recommendation is computed.

## 20. Backend startup

From `backend/`:

```bash
uvicorn app.main:app --reload --port 8000
```

## 21. Frontend startup

From `frontend/`:

```bash
npm run dev
```

Then open <http://localhost:3000>. For a production build:

```bash
npm run build
```

```bash
npm start
```

## 22. Running tests

Backend, from `backend/`:

```bash
python -m pytest
```

Frontend, from `frontend/`:

```bash
npm run lint
```

```bash
npm run typecheck
```

```bash
npm test
```

```bash
npm run build
```

Last recorded results: **94 backend tests passed**, **11 frontend tests passed**, and ESLint, `tsc` and `next build` all succeeded. See [docs/TESTING.md](docs/TESTING.md).

## 23. Troubleshooting

| Symptom | Fix |
|---|---|
| UI shows "Cannot reach the StockWise API" | Start the backend on port 8000, or set `NEXT_PUBLIC_API_BASE_URL` and restart `npm run dev` |
| CORS error in the browser console | Add your frontend origin to `CORS_ORIGINS` |
| `409 duplicate_import` | That exact file is already imported. Activate its dataset in Data Management |
| `422 insufficient_history` | The product has fewer than 14 days of history |
| Want a clean database | Run `python -m scripts.seed --reset` |
| PowerShell blocks `Activate.ps1` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or call `.venv\Scripts\python -m …` directly |

## 24. Known limitations

- Point forecasts only. There are no prediction intervals, so safety stock is heuristic rather than service-level based.
- A single holdout window decides model selection. Rolling-origin backtesting would be more robust.
- Missing dates are assumed to be zero sales. Stockout-censored demand, promotions, prices and holidays are not modelled.
- No authentication or multi-user support. It runs locally with SQLite.
- Recommendation history is not persisted. Recommendations are recomputed on request.
- Returns (negative quantities) are rejected, not netted.
- The bundled PostCSS inside Next.js 15.5.28 has an open `npm audit` advisory. It is a build-time tool that only processes our own CSS. The fix requires upgrading to Next 16, which is a breaking change, so it was not done.
- No Docker setup is provided.

## 25. Reproducibility

- The sample data is generated with fixed seed 42, and a test asserts the committed CSV matches the generator.
- The random forest uses `random_state=42` and `n_jobs=1`, and a test asserts identical predictions across fits. Re-running `scripts.seed` gives the same model selections.
- Python dependencies are pinned in `requirements.txt`. Frontend versions are locked in `package-lock.json`.
- The schema is created by Alembic migration `0001_initial_schema`.

## 26. Demo instructions

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for a timed walkthrough. It covers: start both servers, open the app, load the sample, view a validation report, generate a forecast, compare metrics, configure inventory, read the recommendations and restart to show persistence. It also shows the invalid CSV `data/sample_sales_invalid.csv` and its error report.

### Further documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/API.md](docs/API.md)
- [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md)
- [docs/TESTING.md](docs/TESTING.md)
- [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md)
- [docs/AI_TOOL_USAGE.md](docs/AI_TOOL_USAGE.md)
- [docs/TECHNICAL_INTERVIEW_PREP.md](docs/TECHNICAL_INTERVIEW_PREP.md)
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
- [docs/SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md)
