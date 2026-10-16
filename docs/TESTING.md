# Testing

## How to run

Backend, from `backend/` with the virtual environment active:

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

`npm run lint` runs `eslint . --max-warnings=0`, `npm run typecheck` runs `tsc --noEmit`, `npm test` runs Vitest with jsdom and Testing Library, and `npm run build` runs `next build`.

Backend tests use a fresh temporary SQLite file per test. The `engine` fixture in `tests/conftest.py` creates it, and the API tests override the `get_db` dependency, so the development database is never touched.

## Results recorded on 2026-10-16 (Windows 11, Python 3.11.9, Node 22.19.0)

```
backend> python -m pytest
tests\test_api.py ....................                                   [ 21%]
tests\test_csv_validation.py ..................                          [ 40%]
tests\test_forecasting.py .........................                      [ 67%]
tests\test_inventory_policy.py ......................                    [ 90%]
tests\test_persistence.py .........                                      [100%]
============================= 94 passed in 10.83s =============================

frontend> npm test
 ✓ src/lib/api.test.ts (5 tests)
 ✓ src/components/ValidationReportView.test.tsx (2 tests)
 ✓ src/components/InventoryForm.test.tsx (4 tests)
 Test Files  3 passed (3)
      Tests  11 passed (11)

frontend> npm run lint        → eslint . --max-warnings=0 (no output = no problems)
frontend> npm run typecheck   → tsc --noEmit, exit code 0
frontend> npm run build       → ✓ Compiled successfully; 9 static pages generated
```

Re-run these commands yourself before submitting, and paste your own output into `docs/AI_TOOL_USAGE.md`.

## What is covered

### Data validation (`tests/test_csv_validation.py`)

- a valid CSV
- header normalisation and aliases (`Product ID`, `Quantity Sold`)
- a missing required column
- ambiguous duplicate mappings
- invalid, ambiguous (`01/02/2024`), impossible (`2024-02-30`) and future dates
- non-numeric, infinite, missing and negative quantities
- missing and invalid product IDs
- exact duplicates under both `exclude` and `keep` policies
- several transactions on the same day being aggregated
- missing calendar dates reported but not invented
- a trailing gap counted up to the dataset end
- empty and header-only files
- malformed CSV
- non-CSV, binary and wrong-content-type files
- size and row limits
- an invalid optional `unit_price` being reported
- a file with no valid rows

### Forecasting (`tests/test_forecasting.py`)

- MAE and RMSE against hand-computed values, including invalid inputs
- zero-filling and aggregation in the daily series
- extension to the dataset end (a regression test for a bug found during the UI review)
- holdout size bounds
- the baseline using only its trailing window
- seasonal-naive repetition
- **lag features ignoring future values**
- training-matrix target alignment
- random-forest reproducibility and non-negativity
- chronological holdout with identical dates for all models
- metrics recomputed from the stored holdout points
- **the baseline being unaffected by holdout actual values**
- tie-breaking toward the simpler model
- a candidate beating the baseline on a weekly pattern
- constant demand, zero demand, short (low-confidence) history and too-short history
- horizon validation, forecast date alignment and the "horizon longer than holdout" warning
- independence between products
- the sparse-history warning

### Inventory (`tests/test_inventory_policy.py`)

- the reorder point formula
- fixed safety stock vs safety-stock days
- target stock and order quantity
- sufficient stock
- zero stock (critical)
- a stockout before the lead time ends
- the high and moderate thresholds
- zero lead time
- the minimum order quantity and pack-size rounding (including an exact multiple and zero)
- zero demand, which counts as low risk and as overstock when stock is held
- overstock being relative to demand, not absolute stock
- stockout timing with uneven demand
- extension of a short forecast, with a warning
- 8 parametrised invalid configurations
- explanation text containing the computed values

### API (`tests/test_api.py`)

- health and the request-ID header
- OpenAPI exposing every core route
- upload success
- dry-run validation that persists nothing
- upload failures (missing column, no valid rows, unsupported type, empty file)
- a duplicate import (409)
- a new version becoming active, and re-activating an earlier one
- product listing, search, date filtering, a 404 and an invalid date range
- forecast creation and persistence: points, three evaluations, a single selected model that has the lowest MAE, and holdout length matching the test sample count
- a low-confidence forecast with null metrics
- invalid forecast requests and missing resources
- a forecast requested with no dataset loaded
- batch forecasting
- inventory create, conflict and update, plus recommendations before and after a forecast
- risk and overstock changes after an update
- the risk filter
- inventory validation errors, both safety-stock fields at once, and PUT on settings that do not exist
- dashboard KPIs, with forecast demand checked against the stored points
- insights
- sample download and load, including the duplicate case
- a forced 500 that leaks no internal message or traceback
- a structured 404 for unknown routes

### Persistence (`tests/test_persistence.py`)

- Alembic migrations create every model table, and running them twice is safe
- products and daily records stored with aggregation
- a duplicate file rejected without partial writes
- only the latest dataset is active
- the unique constraint on daily records
- **rollback when the bulk insert fails**
- forecast and inventory persistence feeding recommendations
- the sample data being reproducible and matching `data/sample_sales.csv`
- the sample validating cleanly

### Frontend

| Test file | What it checks |
|---|---|
| `src/lib/api.test.ts` | Query building, structured `ApiError` parsing, the network-error message (no fake data), JSON bodies and URL encoding, multipart upload with the duplicate policy |
| `src/components/InventoryForm.test.tsx` | Negative stock blocked with an error message, zero pack size and fractional lead time rejected, typed payload submitted with a single safety-stock method, empty optional fields becoming `null` |
| `src/components/ValidationReportView.test.tsx` | Counts, rejected-row reasons, instructions, duplicate rows and missing values rendered; the invalid-file state |

## Manual end-to-end verification (done in the in-app browser during development)

1. Started on a reset database. The Overview showed the "No sales data loaded yet" empty state.
2. Validated `data/sample_sales_invalid.csv` through the UI. The report showed 11 rows: 4 accepted, 6 rejected (with line numbers and reasons) and 1 duplicate excluded. Screenshot: `screenshots/agent-verification/01-invalid-csv-validation-report.png`.
3. Clicked **Load sample dataset**, then **Generate forecasts for all products**. The toast read "Generated 8 60-day forecast(s)".
4. Edited SKU-1002's stock to 200 in the Inventory form. The recommendation changed to Critical: reorder point 494, order 678 units. The value persisted after reloading the page.
5. Generated a 14-day forecast for SKU-1008 (40 days of history). The "Low confidence: insufficiently validated" alert appeared.
6. Checked every page at 375 px width and found no horizontal overflow. Two layout bugs were found and fixed along the way (see `DEVELOPMENT_WORKFLOW.md`).

### Not automated

- Browser end-to-end tests (Playwright/Cypress) were not added. The flows above were checked by hand.
- Load and performance testing.
- Accessibility auditing beyond semantic labels and roles. Running Lighthouse or axe is a recommended manual step.
