# Screenshots

## `agent-verification/`: captured during development

These were captured by Claude Code in the desktop app's built-in browser while it verified the app end to end on 2026-10-16. They are genuine, but the pane was only about 800 px wide, so they show part of each page.

| File | Shows |
|---|---|
| `01-invalid-csv-validation-report.png` | Validation report for `data/sample_sales_invalid.csv` (11 rows: 4 accepted, 6 rejected) |
| `02-forecast-chart-SKU-1006.jpg` | History and 60-day forecast with the "Forecast starts" marker |
| `03-model-evaluation-and-holdout-SKU-1006.jpg` | MAE/RMSE table and the actual-vs-predicted holdout chart |
| `04-low-confidence-forecast-SKU-1008.jpg` | The low-confidence alert for a 40-day history |
| `05-inventory-reorder-explanation-SKU-1002.jpg` | Expanded recommendation explanation. Taken *before* the horizontal-scroll fix, so a page scrollbar is visible |
| `06-overview-kpis.jpg` | Overview KPIs |
| `07-BUG-BEFORE-FIX-forecast-boundary-drop.jpg` | **Bug evidence**: the forecast line dropping to 0 at the boundary, before the fix described in `docs/DEVELOPMENT_WORKFLOW.md` #2 |

## Screenshots you should capture yourself (full window, 1440×900 or larger)

Run `python -m scripts.seed --reset` first, then start both servers. Save the files in this folder with these names:

- [ ] `10-dashboard-overview.png`: Overview page, top half (KPIs and the history + forecast chart)
- [ ] `11-csv-upload-success.png`: Data Management, after **Import dataset** succeeds with a new CSV (the success toast and the "dataset #N" report)
- [ ] `12-data-quality-report.png`: Data Management, the validation report for `data/sample_sales_invalid.csv`
- [ ] `13-forecast-chart.png`: Demand Forecasting for SKU-1006, 30 days
- [ ] `14-model-evaluation.png`: the model evaluation table and holdout chart
- [ ] `15-inventory-table.png`: the Inventory table with risk badges
- [ ] `16-reorder-explanation.png`: SKU-1001 expanded, with the explanation and calculation panel
- [ ] `17-api-docs.png`: <http://localhost:8000/docs> showing the endpoint list
- [ ] `18-test-results.png`: terminal output of `python -m pytest` (94 passed) and `npm test` (11 passed)
- [ ] `19-mobile-view.png` (optional): DevTools device toolbar at 375 px
- [ ] `codezero/…`: CodeZero screenshots, taken as you do the tasks (see `docs/AI_TOOL_USAGE.md`)

On Windows, Win + Shift + S captures a region. In Chrome, DevTools → Ctrl + Shift + P → "Capture full size screenshot" captures a whole page.

A demo video is optional but recommended: record a screen capture following `docs/DEMO_SCRIPT.md`, for example with the Xbox Game Bar (Win + G) or OBS.
