# Deployment: Render (backend) + Vercel (frontend)

Both platforms have free tiers and deploy straight from the GitHub repository <https://github.com/Gauravmy/stockwise-ai->. You need your own Render and Vercel accounts. Sign in to both with GitHub so they can see the repository.

```
Browser ──▶ Vercel (Next.js, frontend/)  ──fetch──▶  Render (FastAPI, backend/)  ──▶ SQLite (instance disk)
            NEXT_PUBLIC_API_BASE_URL = Render URL      CORS_ORIGINS = Vercel URL
```

## 1. Backend on Render

The repository root contains [`render.yaml`](../render.yaml), a Blueprint that defines the `stockwise-ai-api` service:

| Setting | Value |
|---|---|
| Plan | Free, Python 3.11.9 |
| Root directory | `backend/` |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m scripts.seed --if-empty && uvicorn app.main:app --host 0.0.0.0 --port $PORT …` |
| Health check | `/health` |
| Environment | `CORS_ORIGINS` and `CORS_ORIGIN_REGEX`, preset for `stockwise-ai*.vercel.app` |

Alembic migrations run automatically on startup (`AUTO_MIGRATE=true`).

Steps:

1. Go to <https://dashboard.render.com> and choose **New → Blueprint**.
2. Connect GitHub and pick **Gauravmy/stockwise-ai-**. Render detects `render.yaml`. Click **Apply**.
3. Wait for the first build (a few minutes: pandas and scikit-learn install from wheels). Startup then seeds the synthetic sample, which takes about 10–30 s on the free CPU.
4. Copy the service URL, e.g. `https://stockwise-ai-api.onrender.com`, and check it:
   - `https://<your-render-url>/health` returns `{"status":"ok","database":"ok",...}`
   - `https://<your-render-url>/docs` shows the API docs

## 2. Frontend on Vercel

1. Go to <https://vercel.com/new> and import **Gauravmy/stockwise-ai-**.
2. Set **Root Directory** to `frontend`. The framework is detected as Next.js, and the build is `npm run build`.
3. Under **Environment Variables**, add `NEXT_PUBLIC_API_BASE_URL`, set to your Render URL with no trailing slash, e.g. `https://stockwise-ai-api.onrender.com`.
4. Click **Deploy**.
5. Note the production URL, e.g. `https://stockwise-ai.vercel.app`.

`NEXT_PUBLIC_*` variables are baked in at build time. If you change the Render URL later, redeploy the frontend.

## 3. Connect them (CORS)

The backend accepts browser requests only from the origins it is configured for. The defaults are:

- `CORS_ORIGINS=https://stockwise-ai.vercel.app`
- `CORS_ORIGIN_REGEX=^https://stockwise-ai[a-z0-9-]*\.vercel\.app$`, which also covers preview URLs such as `stockwise-ai-git-main-<team>.vercel.app`

If your Vercel URL does **not** start with `stockwise-ai`, change `CORS_ORIGINS` to that exact URL in Render → service → **Environment**. Saving the change redeploys the service.

## 4. Verify the live deployment

- [ ] Open the Vercel URL. The Overview shows "synthetic sample data", 8 products and the charts.
- [ ] Demand Forecasting: generate a forecast for SKU-1006 and check that the metrics table appears.
- [ ] Inventory: edit one product and check that the change persists after reloading the page.
- [ ] Data Management: validating `data/sample_sales_invalid.csv` shows the report.
- [ ] In the browser DevTools Network tab, requests go to the Render URL and none fail with a CORS error.

## Free-tier behaviour and limitations

| Behaviour | Effect |
|---|---|
| **Cold starts** | Free Render services sleep after about 15 minutes idle. The first request then takes about 30–60 s, and the UI may briefly show "Cannot reach the StockWise API" with a retry hint. Open the backend `/health` URL a minute before a demo to wake it. |
| **Ephemeral disk** | The SQLite file lives on the instance disk, which is wiped on every restart or redeploy. The start command re-seeds the synthetic sample, so the demo always works, but **uploads and inventory edits are lost on restart**. For durable data, either attach a Render persistent disk (paid) and set `DATABASE_URL=sqlite:////var/data/stockwise.db`, or move to PostgreSQL. |
| **Single instance** | SQLite plus one uvicorn process. That is fine for a demo, not for concurrent multi-user writes. |
| **No authentication** | Anyone with the URL can upload data or edit inventory. Upload size and row limits still apply. Share the link only with reviewers. |

## Updating the deployment

Push to `main`. Render (`autoDeploy: true`) and Vercel both redeploy automatically:

```bash
git push
```
