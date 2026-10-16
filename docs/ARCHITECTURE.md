# Architecture

## Overview

```
┌──────────────────────────── Browser ────────────────────────────┐
│ Next.js 15 (App Router, client components)                       │
│  pages: / · /forecasting · /inventory · /data · /insights        │
│  src/lib/api.ts  ── typed fetch client, ApiError, no fake data   │
│  src/lib/useApi.ts ─ loading / error / reload state per request  │
└───────────────┬──────────────────────────────────────────────────┘
                │ HTTP JSON / multipart  (NEXT_PUBLIC_API_BASE_URL)
┌───────────────▼──────────────── FastAPI (app/main.py) ───────────┐
│ middleware: CORS (local origins) · request-id + timing log       │
│ exception handlers (app/errors.py) → {"error": {...}}            │
│ routes (app/api/routes/*)  — parse/validate input, status codes  │
│        │                                                         │
│ services (app/services/*)  — business logic, transactions        │
│   csv_validation.py  (pure)   inventory_policy.py (pure)         │
│   datasets.py  products.py  forecasts.py  inventory.py           │
│   analytics.py  sample_data.py                                   │
│        │                         │                               │
│ ml (app/ml/*)  (pure)            │                               │
│   forecasting.py  metrics.py     │                               │
│                                  ▼                               │
│ db (app/db/*): SQLAlchemy models, session, Alembic migrations    │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
            SQLite  (backend/stockwise.db)
```

## Design principles

- **Pure core, thin edges.** CSV validation (`csv_validation.py`), forecasting (`ml/forecasting.py`, `ml/metrics.py`) and the inventory maths (`inventory_policy.py`) import nothing from FastAPI and never touch the database. That lets them be unit-tested directly; see `tests/test_csv_validation.py`, `test_forecasting.py` and `test_inventory_policy.py`.
- **Services own persistence.** Each mutating service function commits on success and rolls back on any exception, for example `commit_dataset` in `services/datasets.py`. Route handlers only translate between HTTP and service calls.
- **One error contract.** Every error becomes `{"error": {code, message, details, request_id}}`:
  - Domain errors (`AppError` subclasses) map to 404, 409, 413, 415 or 422.
  - Pydantic validation errors become `422 invalid_request` with a per-field list.
  - Unknown exceptions are logged with a traceback, but the client receives a generic `500 internal_error`.
- **No hidden fallbacks.** If the backend is unreachable, the frontend shows a `network_error` with the configured URL. It never substitutes placeholder data.

## Request flows

### CSV import

1. The UI calls `POST /datasets/validate` with the file. `_read_limited` reads at most `MAX_UPLOAD_BYTES + 1` bytes, so an oversized upload is rejected without being buffered in full.
2. `validate_sales_csv` runs the checks in this order:
   1. extension and content type
   2. size
   3. empty or binary content
   4. UTF-8 decoding
   5. pandas parse with `dtype=str` and strict bad-line handling
   6. row limit
   7. header mapping
   8. vectorised row checks
   9. duplicates
   10. aggregation
   11. product attributes
   12. coverage
   13. the report
3. The UI shows the report and preview. **Import dataset** calls `POST /datasets/upload`, which runs the same validation again on the server and then `commit_dataset`. That function, in one transaction:
   - checks the SHA-256 against earlier imports
   - upserts products
   - deactivates the other datasets
   - inserts the dataset row and bulk-inserts the daily sales records

### Forecast

1. `POST /forecasts` → `services.forecasts.create_forecast` loads the product's daily records from the active dataset.
2. It calls `forecast_product(..., end_date=active.date_end)`, which is pure.
3. It persists a `ForecastRun` with its `ForecastPoint` and `ModelEvaluation` children (holdout points are stored as JSON) in a single commit.

### Recommendations

`GET /inventory/recommendations` → `build_recommendations`:

1. Loads the products in the active dataset with their `InventorySetting`.
2. Finds the latest `ForecastRun` per product with a `max(id)` group-by.
3. Calls `inventory_policy.recommend(config, daily_forecast)` for each product.

Results are computed on request and not stored, so they always reflect the current settings.

## Data model

```
products 1─┬─* sales_records *─1 datasets
           ├─* forecast_runs *─1 datasets
           │       ├─* forecast_points
           │       └─* model_evaluations
           └─1 inventory_settings
```

Constraints and indexes are listed in [README §6](../README.md#6-database-schema).

- **Primary keys:** integer surrogate keys throughout. `products.product_id` is the unique natural key exposed in the API.
- **Uniqueness:** daily records are unique per (dataset, product, date). Forecast points are unique per (run, date).
- **Referential integrity:** SQLite foreign keys are enforced with `PRAGMA foreign_keys=ON` in `db/session.py`.
- **Timestamps:** stored as UTC through the `UTCDateTime` type decorator. SQLite drops timezone information, so the decorator re-attaches UTC on load and the API emits `…Z` timestamps.

## Configuration and logging

- **Configuration:** `app/config.py` (pydantic-settings) reads environment variables or `.env`. See README §17.
- **What gets logged:** request method, path, status, duration and request ID, plus summary counts per import or forecast (rows, accepted, rejected, product, model).
- **What never gets logged:** uploaded file contents and row values.

## Frontend structure

| Path | Contents |
|---|---|
| `src/components/layout/AppShell.tsx` | Sidebar (desktop) or collapsible top bar (mobile), plus the toast provider |
| `src/components/ui/index.tsx` | Card, StatCard, Button, Alert, RiskBadge, table helpers, Empty/Error states |
| `src/components/charts/index.tsx` | Recharts wrappers: DemandChart, HoldoutChart, CategoryTrendChart, RiskBarChart |
| `src/components/InventoryForm.tsx` | React Hook Form + Zod; mirrors the backend constraints |
| `src/components/ValidationReportView.tsx` | Renders a validation report |

Chart colours follow a fixed, colour-vision-deficiency-checked categorical order: blue = history/actual, orange = forecast. Status colours are always paired with an icon and a text label.

## Why not microservices or a task queue?

Forecasting one product takes about 0.3–1.5 s locally, and a batch of 8 products takes about 8 s, so synchronous requests are acceptable for this scope. With thousands of SKUs, batch forecasting should move to a background worker; see the production improvements in [TECHNICAL_INTERVIEW_PREP.md](TECHNICAL_INTERVIEW_PREP.md).
