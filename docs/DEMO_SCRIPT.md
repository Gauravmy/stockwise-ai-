# Demo script (about 8 minutes)

## Preparation

Do this once, before recording.

1. Open terminal 1 and go to the backend:

   ```bash
   cd backend
   ```

2. Activate the virtual environment (Windows PowerShell):

   ```bash
   .venv\Scripts\Activate.ps1
   ```

3. Reset the database and load the synthetic sample with demo inventory and 60-day forecasts:

   ```bash
   python -m scripts.seed --reset
   ```

4. Have `data/sample_sales_invalid.csv` ready to upload.
5. Close other browser tabs and set the browser zoom to 100%.

## 1. Start the backend and frontend (30 s)

Terminal 1, from `backend/`:

```bash
uvicorn app.main:app --port 8000
```

Terminal 2, from `frontend/`:

```bash
npm run dev
```

Show <http://localhost:8000/health> returning `{"status":"ok","database":"ok",...}`, and the interactive API docs at <http://localhost:8000/docs>.

## 2. Open the application (30 s)

Open <http://localhost:3000>. Point out:

- the "synthetic sample data" notice
- the KPIs: 8 products, products at risk, products requiring reorder, 30-day forecast demand
- the history + forecast chart, with the dashed forecast line after the "Forecast starts" marker
- the risk bar chart

Change **Next 30 days** to **Next 7 days** and the category to **Beverages** to show that the filters change the numbers.

## 3. Load or upload the sample dataset (45 s)

Go to **Data Management**.

1. Click **Sample CSV** to download it. This is served by the backend.
2. Choose the downloaded file and click **Validate & preview**. The report shows 4,106 rows, all accepted, 0 rejected and 460 aggregated same-day transactions.
3. Click **Import dataset**. Because the seed already imported this exact file, the app replies with **"This exact file was already imported as dataset 1"** (`409`). Explain the SHA-256 duplicate-import guard and the versioning policy.

## 4. Show a validation report on an invalid CSV (60 s)

Choose `data/sample_sales_invalid.csv` and click **Validate & preview**. Point out:

- **11 rows: 4 accepted, 6 rejected, 1 duplicate, 1 aggregated.**
- The rejected rows, with line numbers:

  | Line | Problem |
  |---|---|
  | 5 | `01/02/2025`: an ambiguous date that is not guessed |
  | 6 | `abc` |
  | 7 | negative quantity |
  | 8 | missing product ID |
  | 9 | missing quantity |
  | 12 | future date |

- The `unit_price=free` warning: the price is left empty but the row is kept.
- The "How to fix" instructions.
- The missing-dates warning (70%) and the "only 10 days of history" warning.

Optionally, rename a copy of the file to `.txt` and upload it to show the `415` error message.

## 5. Select a product and horizon, and generate a forecast (60 s)

Go to **Demand Forecasting**.

1. Choose **SKU-1006 (A5 Notebook)** and a **30 days** horizon, then click **Generate forecast**. A toast confirms the new run.
2. Show the chart. History is solid blue, the forecast is dashed orange, and the weekday pattern continues into the forecast.
3. Change **History from** to show that the date filter only affects the display.

## 6. Compare model evaluation metrics (60 s)

Still on Demand Forecasting, open the **Model evaluation** table. The holdout runs 2025-06-03 → 2025-06-30 (28 days):

| Model | MAE | RMSE |
|---|---|---|
| Moving average | 10.43 | 12.32 |
| Seasonal naive | 6.64 | 8.84 |
| Random forest (selected) | 3.90 | 5.22 |

Read out the selection reason ("62.6% lower") and show the **Actual vs predicted** chart.

Then switch to **SKU-1002**: the **baseline wins** there. Then switch to **SKU-1008** and generate a 14-day forecast, which shows the **Low confidence** alert with no metrics.

## 7. Configure inventory and lead time (45 s)

Go to **Inventory**.

1. Open **How recommendations are calculated** and walk through the formulas.
2. Click **Edit** on SKU-1002. Change **Current stock** to 200, keep the lead time at 14 days, and click **Save changes**.
3. The row becomes **Critical**: reorder point 494, order quantity 678.

## 8. Reorder recommendations (45 s)

Expand **SKU-1001** and read its explanation:

- lead-time demand 422 + safety stock 214 = reorder point 636
- stock 250, so a reorder is recommended
- target 1,238 − 250 = 988
- adjusted to **1,008** for the minimum order of 100 and pack size of 24

## 9. Explain stockout risk (30 s)

On SKU-1001, stock runs out in about **5.7 days**, before the **10-day** lead time ends. So it is **Critical**, not just High.

Contrast it with **SKU-1007**: 1,500 units cover about 220 days, which is above the 90-day threshold, so it is flagged as **Overstock** with **Low** risk.

Filter the table by **Potential overstock**, then open **Insights & Reports** to show the reorder priorities and the overstock list.

## 10. Persistence after a restart (30 s)

Stop the backend with Ctrl+C and start it again:

```bash
uvicorn app.main:app --port 8000
```

Reload the Inventory page. SKU-1002 still shows stock 200, and Demand Forecasting → **Forecast history** still lists the earlier runs.

## 11. Close (15 s)

Run the backend tests, from `backend/`:

```bash
python -m pytest
```

It should report **94 passed**. Optionally run the production build too, from `frontend/`:

```bash
npm run build
```

## Screenshot checklist

See `screenshots/README.md` for the exact list and file names.
