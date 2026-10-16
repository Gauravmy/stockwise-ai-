# Submission checklist

## A. Requirement status

Status values: ✅ complete and verified · 🟡 implemented, not fully verified · ⛔ blocked or incomplete. "Verified" means checked by a command, an automated test or a manual browser run during development on 2026-10-16.

### Application

| Item | Status | Evidence |
|---|---|---|
| Backend starts | ✅ | `uvicorn app.main:app`; `/health` → `{"status":"ok","database":"ok"}` |
| Frontend starts | ✅ | `npm run dev`; all pages loaded in the browser |
| Database initialises from a clean state | ✅ | `scripts.init_db --reset`; `test_alembic_migrations_create_schema_matching_models` |
| Sample data loads reproducibly | ✅ | `scripts.seed --reset` run twice with identical model selections; `test_sample_data_is_reproducible_and_matches_committed_file` |
| CSV upload works | ✅ | `test_upload_success_creates_active_dataset`; UI "Load sample dataset" |
| Invalid CSVs return meaningful errors | ✅ | 18 validation tests; UI report for `sample_sales_invalid.csv` |
| Validation reports are accurate | ✅ | 11 = 4 accepted + 6 rejected + 1 duplicate, checked by hand |
| Forecasts computed dynamically | ✅ | `POST /forecasts`; persisted points checked in tests |
| Baseline and candidates compared fairly | ✅ | Same holdout dates asserted in tests |
| MAE/RMSE on valid holdout predictions | ✅ | `test_evaluation_is_chronological…`, `test_baseline_evaluation_ignores_holdout_values` |
| Insufficient history handled honestly | ✅ | Low-confidence run with null metrics; 422 below 14 days |
| Inventory settings persist | ✅ | API test, plus a UI edit that survived a reload |
| Recommendations follow the documented formulas | ✅ | 22 inventory tests; explanation numbers checked by hand |
| Stockout-risk explanations accurate | ✅ | Explanation tests; SKU-1001 5.7 days < 10-day lead time → critical |
| Overstock follows the documented rules | ✅ | `test_overstock_uses_coverage_relative_to_demand` |
| Dashboard charts use backend responses | ✅ | `test_dashboard_and_insights` cross-checks the stored points |
| Product and date filters work | ✅ | API tests; UI product, date, category and period filters used |
| Forecast history persists | ✅ | `GET /forecasts`; forecast-history table |
| API documentation available | ✅ | `/docs` returned HTTP 200; `docs/API.md` |
| Persistence after a backend restart | ✅ | Restarted backend; data and forecasts still served |

### Quality

| Item | Status | Evidence |
|---|---|---|
| Backend tests executed | ✅ | 94 passed |
| Frontend lint executed | ✅ | `eslint . --max-warnings=0` clean |
| TypeScript checks executed | ✅ | `tsc --noEmit` exit code 0 |
| Production build executed | ✅ | `next build` succeeded; 9 static pages |
| Frontend tests executed | ✅ | 11 passed |
| Remaining failures documented | ✅ | None failing. Remaining limitations are in README §24 |
| No hardcoded fake metrics | ✅ | All values come from computations; demo inventory *configuration* is in `scripts/seed.py` |
| No misleading model claims | ✅ | The baseline wins on 3 of 7 products, and this is reported |
| No unresolved critical defects | ✅ | Known bugs fixed, with regression tests |
| Browser end-to-end automation | ⛔ | Not implemented. The flows were checked by hand |
| `npm audit` clean | 🟡 | One advisory in the PostCSS bundled with Next 15. The fix needs Next 16 |

### Delivery

| Item | Status |
|---|---|
| README, architecture, API, model-selection docs | ✅ |
| Technical interview prep, demo script | ✅ |
| Evidence checklist (`docs/AI_TOOL_USAGE.md`, `screenshots/README.md`) | ✅ |
| **CodeZero usage and evidence** | ⛔ **Not done.** You must sign up, use CodeZero on real tasks and record the evidence. **Do not claim it before then.** |
| Full-size screenshots / video | ⛔ To capture manually (`screenshots/README.md`) |
| Git commit / GitHub push | ⛔ The repo is initialised, but nothing is committed or pushed |

## B. Pre-submission steps

- [ ] Run `git status`. It must not list `stockwise.db`, `.venv/`, `node_modules/`, `.next/` or any `.env` file; all of these are ignored.
- [ ] Remove temporary files. Nothing should remain outside the ignored paths.
- [ ] Confirm `data/sample_sales.csv` and `data/sample_sales_invalid.csv` are present.
- [ ] Clean-environment test: clone into a new folder, follow README §16–21, and check `seed --reset`, both servers and the UI.
- [ ] Backend tests, from `backend/`:

  ```bash
  python -m pytest
  ```

- [ ] Frontend checks, from `frontend/`:

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

- [ ] Open <http://localhost:8000/docs> and check that every endpoint is listed.
- [ ] Re-read the README to confirm the commands are accurate on your machine.
- [ ] Do a full demo run-through (`docs/DEMO_SCRIPT.md`).
- [ ] Complete the CodeZero tasks and evidence (`docs/AI_TOOL_USAGE.md` §3–§6).
- [ ] Capture the screenshots (and optionally a video).

## C. Publishing to GitHub (do this yourself)

These steps need your GitHub account, so they were not run.

1. Create an **empty** repository on GitHub named `stockwise-ai`, with no README or license.
2. From the project root, check what will be committed:

   ```bash
   git status
   ```

3. Stage everything (the `.gitignore` excludes local files):

   ```bash
   git add -A
   ```

4. Commit:

   ```bash
   git commit -m "StockWise AI: demand forecasting and inventory optimization platform"
   ```

5. Add the remote, replacing the placeholder with your repository URL:

   ```bash
   git remote add origin https://github.com/<your-username>/stockwise-ai.git
   ```

6. Push:

   ```bash
   git push -u origin main
   ```

Commit your CodeZero-assisted changes as **separate commits**, so their diffs are part of the evidence.

## D. Submission email draft

```
Subject: Software Engineer Intern Assignment – StockWise AI – <Your Name>

Dear Edvexa Hiring Team,

Please find my submission for the Software Engineer Intern technical assignment.

Repository: <GITHUB_REPOSITORY_URL>
Demo video: <DEMO_VIDEO_URL>   (optional)

StockWise AI is a local full-stack application (FastAPI + SQLite + scikit-learn backend,
Next.js + TypeScript frontend) that:
- imports and validates sales CSVs with a detailed data-quality report and versioned datasets;
- forecasts product demand for a configurable horizon, comparing a moving-average baseline
  with seasonal-naive and random-forest candidates on a chronological holdout (MAE/RMSE);
- turns forecasts into explainable reorder recommendations with stockout and overstock risk.

Verification: 94 backend tests and 11 frontend tests pass; ESLint, TypeScript and the
production build succeed. Setup takes a few commands (README sections 16–21), and
`python -m scripts.seed --reset` loads a synthetic sample dataset.

Development workflow: I used Claude Code as the primary coding agent and CodeZero for
<DESCRIBE THE ACTUAL CODEZERO TASKS YOU COMPLETED>. Evidence is in docs/AI_TOOL_USAGE.md
and screenshots/.

Documentation: README.md, docs/ARCHITECTURE.md, docs/API.md, docs/MODEL_SELECTION.md,
docs/TESTING.md.

Thank you for your time. I look forward to discussing the project.

Kind regards,
<Your Name>
<Phone> · <Email> · <LinkedIn URL>
```
