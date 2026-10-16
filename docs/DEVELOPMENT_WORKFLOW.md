# Development workflow

This document records how the project was actually built, including the real defects found and how each was verified. **CodeZero has not been used yet**; see the "CodeZero status" section and `docs/AI_TOOL_USAGE.md`.

## Tools actually used

| Tool | Used for |
|---|---|
| **Claude Code** (desktop app, model Claude Opus 5.5) | Inspecting the workspace, implementing all backend and frontend code, running commands (pip, pytest, npm, alembic), driving the in-app browser for end-to-end checks, and writing documentation |
| Python 3.11.9, pytest 8.3.4 | Backend implementation and tests |
| Node 22.19.0, npm 10.9.3, Next.js 15.5.28, Vitest 3.2.7 | Frontend implementation, tests and build |
| Git 2.51 | Version control (`git init -b main`) |
| CodeZero | **Not yet used.** It requires creating an account and installing a VS Code extension, which the developer must do personally |

## Phases followed

| # | Phase | Verification performed |
|---|---|---|
| 1 | Inspect workspace | The directory was empty and was not a git repo. Detected Python 3.11.9, Node 22.19.0, npm 10.9.3, git 2.51; `py` launcher absent |
| 2 | Backend foundation, schema, sample data | `scripts.seed --reset` imported 4,106 synthetic rows |
| 3 | CSV ingestion and validation | Smoke test on the sample, then 18 unit tests |
| 4–5 | Forecasting and chronological evaluation | Per-product holdout metrics printed and checked for plausibility (the baseline wins on 3 of 7 products) |
| 6 | Inventory policy | Hand-checked explanation numbers (636 = 422 + 214) |
| 7 | REST API | Endpoints exercised with curl, including error paths |
| 8–9 | Frontend wired to the API | `tsc`, ESLint, `next build`, then manual end-to-end runs in the in-app browser |
| 10 | Tests and bug fixes | 94 backend and 11 frontend tests passing |
| 11 | Documentation | Every number in the docs was copied from real command output |
| 12 | CodeZero evidence | **Pending:** needs the developer's account |
| 13 | Demo and submission prep | Checklist and email draft written; nothing pushed |

## Real defects found and fixed during development

Each entry below happened during this build. They are good candidates for the "genuine debugging example" evidence.

### 1. Validation crashed when every date in a file was invalid

- **Symptom:** `test_upload_failures` and `test_no_valid_rows_marks_report_invalid` failed with `TypeError: Invalid comparison between dtype=datetime64[ns] and date`.
- **Root cause:** `parsed_dates.dt.date > today`. When every value is `NaT`, pandas keeps the `datetime64` dtype instead of returning `date` objects, so the comparison raises.
- **Fix** in `app/services/csv_validation.py`: compare `parsed_dates > pd.Timestamp(today)` instead.
- **Verified:** the full suite passed afterwards. The tests were written *before* the bug was noticed and caught it on the first run.

### 2. Forecasts for intermittent products started inside the historical period

- **Symptom:** in the browser, the Overview "Historical and forecast demand" chart showed the forecast line diving to ≈0 at the history/forecast boundary. Screenshot: `screenshots/agent-verification/07-BUG-BEFORE-FIX-forecast-boundary-drop.jpg`.
- **Investigation:** the API's `demand_series` contained a forecast point dated **2025-06-30**, which is the last *history* date, with value 0.893.
- **Root cause:** `build_daily_series` ended each product's series at that product's last sale. SKU-1004 (intermittent demand) had no sale on 2025-06-30, so:
  - its history ended a day early
  - its forecast started on a day that is already in the data
  - trailing zero-sales days were silently dropped, which biases the baseline upward
- **Fix:**
  - `build_daily_series(..., end_date)` extends the series to the dataset end, filling zeros. This matches the documented missing-date policy.
  - `create_forecast` passes `active.date_end`.
  - Product statistics and the validation coverage report now also run to the dataset end.
- **Regression tests:** `test_series_extends_to_dataset_end_with_zero_days`, `test_forecast_starts_after_dataset_end_for_product_with_trailing_gap` and `test_coverage_counts_trailing_gap_until_dataset_end`.
- **A test that needed updating, and why:** `test_forecast_low_confidence_for_short_history` started failing. Its "short history" product P2 had been placed in the *first* 30 days of a 120-day dataset, so under the corrected policy it really has 120 days of history, 90 of them zero-filled. The fixture was changed so P2 is a genuinely new product whose sales start on day 91. The assertion was **not** weakened.
- **Verified:** 94 tests pass, and the API now shows every product's forecast starting 2025-07-01.

### 3. The sample generator produced 16 exact-duplicate rows

- **Symptom:** the first validation of the synthetic sample reported `duplicate_rows: 16`.
- **Root cause:** the generator split some daily totals into two transactions. When the split was even (e.g. 4 → 2 + 2), the two rows were identical and the default duplicate policy excluded one, losing legitimate sales.
- **Fix** in `app/services/sample_data.py`: uneven splits only. The sample now validates with 0 duplicates and 460 aggregated rows.
- **Lesson:** this is the trade-off the duplicate policy documents. Without a transaction ID, identical rows are ambiguous, which is why `duplicate_policy=keep` exists.

### 4. Page-level horizontal scroll on the Inventory table

- **Symptom:** a horizontal scrollbar appeared on the whole page, even though the table sits in an `overflow-x-auto` wrapper.
- **Investigation:** in the browser console, `document.documentElement.scrollWidth` was 1112 but `body.scrollWidth` was 1009.
- **Root cause:** Tailwind `sr-only` labels inside table headers are `position: absolute`. The scroll wrapper was not a positioned element, so they escaped its clipping.
- **Fix:** `relative` on the `TableWrap` container.

### 5. Cards overflowing at a 375 px phone width

- **Root cause:** CSS grid items default to `min-width: auto`, so a wide table stretched its grid column.
- **Fix:** `min-w-0` on `Card`.
- **Verified:** for all five pages, measured `scrollWidth === clientWidth === 375` in the browser.

### 6. Frontend tests failed with "React is not defined"

- **Root cause:** `@vitejs/plugin-react` 6 did not apply under Vitest 3, so JSX was compiled with the classic runtime.
- **Fix:** removed the plugin and set `esbuild: { jsx: "automatic" }` in `vitest.config.mts`.

### 7. Timestamps lost their timezone

- **Root cause:** SQLite does not store tzinfo, so `created_at` came back naive and browsers would have read it as local time.
- **Fix:** a `UTCDateTime` type decorator re-attaches UTC on load, and the API now emits `…Z`.

### 8. Dependency security

- **Problem:** `create-next-app@15.1.0` installs Next 15.1.0, which has published security advisories.
- **Fix:** upgraded to the latest 15.x patch (15.5.28).
- **Remaining:** one `npm audit` finding remains, for the PostCSS copy bundled inside Next. Fixing it requires the breaking Next 16 upgrade, so it is documented rather than forced.

## Engineering decisions and alternatives

| Decision | Alternatives considered | Reason |
|---|---|---|
| (s, S) reorder policy: order up to target when stock ≤ reorder point | Always order `max(0, target − stock)` | Avoids recommending small top-up orders when stock is comfortably above the reorder point. The order-up-to gap is still returned for transparency |
| A dataset version per upload, with one active | Merge uploads into one history | Immutable versions make every forecast reproducible and auditable, and `file_sha256` prevents double imports |
| Missing dates treated as zero, with a warning above 10% | Treat them as missing and interpolate | Transaction exports normally omit zero days. Interpolating would invent sales |
| Strict ISO dates | Guessing day/month order | `01/02/2025` is ambiguous, and the brief forbids inventing values |
| A dry-run `/validate` endpoint before `/upload` | A server-side "staged upload" table | Stateless and simpler. The file is validated again on commit, so the client cannot skip validation |
| Synchronous forecasting | A Celery/RQ queue | About 8 s for a batch of 8 products is acceptable locally. A queue is listed as a production improvement |

## CodeZero status

**Not used yet.** Nothing in this repository was generated by CodeZero. To integrate it genuinely, follow `docs/AI_TOOL_USAGE.md` §3 and record the evidence there.
