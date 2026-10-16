"use client";

import { Play } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { DemandChart, HoldoutChart, type DemandPoint } from "@/components/charts";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Spinner,
  TableWrap,
  Td,
  Th,
  WarningList,
  inputClass,
} from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtNumber, MODEL_LABELS } from "@/lib/format";
import type { ForecastRunDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const HORIZONS = [7, 14, 30, 60, 90];

function addDays(iso: string, days: number) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function ForecastingInner() {
  const notify = useToast();
  const params = useSearchParams();
  const products = useApi(() => api.listProducts(), []);
  const [productId, setProductId] = useState<string>("");
  const [horizon, setHorizon] = useState(30);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [run, setRun] = useState<ForecastRunDetail | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Default product: from ?product= or first product.
  useEffect(() => {
    if (!products.data?.items.length || productId) return;
    const fromUrl = params.get("product");
    const match = products.data.items.find((p) => p.product_id === fromUrl);
    setProductId(match ? match.product_id : products.data.items[0].product_id);
  }, [products.data, productId, params]);

  const selected = products.data?.items.find((p) => p.product_id === productId);

  // Default history window: last 120 days of the product's history.
  useEffect(() => {
    if (!selected?.last_date || !selected.first_date) return;
    const start = addDays(selected.last_date, -119);
    setStartDate(start < selected.first_date ? selected.first_date : start);
    setEndDate(selected.last_date);
  }, [selected?.product_id, selected?.first_date, selected?.last_date]);

  const dateError = startDate && endDate && startDate > endDate ? "Start date must be on or before end date." : undefined;
  const history = useApi(
    () => api.getProduct(productId, { start_date: startDate || undefined, end_date: endDate || undefined }),
    [productId, startDate, endDate],
    Boolean(productId) && !dateError,
  );
  const runs = useApi(() => api.listForecasts({ product_id: productId, limit: 10 }), [productId], Boolean(productId));

  // Show the latest stored forecast for the product.
  useEffect(() => {
    setRun(null);
    const latest = runs.data?.items[0];
    if (!latest) return;
    let cancelled = false;
    setRunLoading(true);
    api
      .getForecast(latest.id)
      .then((r) => !cancelled && setRun(r))
      .catch((e) => !cancelled && notify("error", e.message))
      .finally(() => !cancelled && setRunLoading(false));
    return () => {
      cancelled = true;
    };
  }, [runs.data, notify]);

  async function generate() {
    setGenerating(true);
    try {
      const r = await api.createForecast(productId, horizon);
      setRun(r);
      notify("success", `Forecast #${r.id} created for ${r.product_id} (${r.horizon_days} days).`);
      await Promise.all([runs.reload(), products.reload()]);
    } catch (e) {
      notify("error", (e as Error).message);
    } finally {
      setGenerating(false);
    }
  }

  async function openRun(id: number) {
    setRunLoading(true);
    try {
      setRun(await api.getForecast(id));
    } catch (e) {
      notify("error", (e as Error).message);
    } finally {
      setRunLoading(false);
    }
  }

  const chartData: DemandPoint[] = useMemo(() => {
    const rows: DemandPoint[] = (history.data?.sales ?? []).map((s) => ({ date: s.date, actual: s.quantity, forecast: null }));
    if (run && run.product_id === productId) {
      for (const p of run.points) rows.push({ date: p.date, actual: null, forecast: p.predicted_quantity });
    }
    return rows;
  }, [history.data, run, productId]);

  const baseline = run?.evaluations.find((e) => e.role === "baseline");
  const selectedEval = run?.evaluations.find((e) => e.is_selected);

  if (products.error) return <ErrorState error={products.error} onRetry={products.reload} />;
  if (products.loading && !products.data) return <Spinner />;
  if (!products.data?.items.length)
    return (
      <>
        <PageHeader title="Demand Forecasting" />
        <EmptyState title="No products available" description="Load a dataset on the Data Management page first." />
      </>
    );

  return (
    <>
      <PageHeader
        title="Demand Forecasting"
        description="Each forecast evaluates a moving-average baseline and two candidate models on the same chronological holdout, then selects the model with the lowest holdout MAE."
      />

      <Card className="mb-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Product" htmlFor="product">
            <select id="product" className={inputClass} value={productId} onChange={(e) => setProductId(e.target.value)}>
              {products.data.items.map((p) => (
                <option key={p.product_id} value={p.product_id}>
                  {p.product_id} — {p.name ?? "Unnamed"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Forecast horizon" htmlFor="horizon" hint="1–90 days supported">
            <select id="horizon" className={inputClass} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
              {HORIZONS.map((h) => <option key={h} value={h}>{h} days</option>)}
            </select>
          </Field>
          <Field label="History from" htmlFor="start" error={dateError}>
            <input id="start" type="date" className={inputClass} value={startDate} min={selected?.first_date ?? undefined} max={selected?.last_date ?? undefined} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          <Field label="History to" htmlFor="end">
            <input id="end" type="date" className={inputClass} value={endDate} min={selected?.first_date ?? undefined} max={selected?.last_date ?? undefined} onChange={(e) => setEndDate(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <Button className="w-full" onClick={generate} loading={generating} disabled={!productId}>
              <Play className="h-4 w-4" aria-hidden /> Generate forecast
            </Button>
          </div>
        </div>
        {selected && (
          <p className="mt-3 text-xs text-ink-muted">
            {selected.history_days} days of history ({fmtDate(selected.first_date)} – {fmtDate(selected.last_date)}), {selected.observed_days} days with recorded sales,
            average {fmtNumber(selected.avg_daily_quantity, 1)} units/day. The date filter changes the displayed history only; models always train on the full history.
          </p>
        )}
      </Card>

      <div className="space-y-4">
        <Card
          title={`Demand — ${productId}`}
          subtitle={run ? `Forecast #${run.id}: ${fmtDate(run.forecast_start)} – ${fmtDate(run.forecast_end)}, ${MODEL_LABELS[run.selected_model]}` : "No forecast generated yet for this product"}
        >
          {history.error ? (
            <ErrorState error={history.error} onRetry={history.reload} />
          ) : history.loading && !history.data ? (
            <Spinner />
          ) : (
            <DemandChart data={chartData} height={320} ariaLabel={`Historical and forecast demand for ${productId}`} />
          )}
        </Card>

        {runLoading && <Spinner label="Loading forecast…" />}

        {run && run.product_id === productId && (
          <>
            {run.confidence === "low" && (
              <Alert tone="warning" title="Low confidence: insufficiently validated">
                {run.selection_reason}
              </Alert>
            )}
            <div className="grid gap-4 sm:grid-cols-3">
              <Card title="Total forecast demand"><p className="tabular text-2xl font-semibold text-navy-900">{fmtNumber(run.total_forecast)}</p><p className="text-xs text-ink-muted">units over {run.horizon_days} days ({fmtNumber(run.total_forecast / run.horizon_days, 1)}/day)</p></Card>
              <Card title="Selected model"><p className="text-base font-semibold text-navy-900">{MODEL_LABELS[run.selected_model]}</p><p className="text-xs text-ink-muted">{run.confidence === "validated" ? "Validated on holdout" : "Not validated"} · created {fmtDateTime(run.created_at)}</p></Card>
              <Card title="Holdout MAE (selected vs baseline)">
                <p className="tabular text-2xl font-semibold text-navy-900">{selectedEval?.mae != null ? fmtNumber(selectedEval.mae, 2) : "—"}<span className="text-sm font-normal text-ink-muted"> vs {baseline?.mae != null ? fmtNumber(baseline.mae, 2) : "—"}</span></p>
                <p className="text-xs text-ink-muted">units/day, lower is better</p>
              </Card>
            </div>

            <Card title="Model evaluation" subtitle={selectedEval?.test_start ? `Chronological holdout ${fmtDate(selectedEval.test_start)} – ${fmtDate(selectedEval.test_end)} (${selectedEval.test_samples} days); trained on ${fmtDate(selectedEval.train_start)} – ${fmtDate(selectedEval.train_end)}` : "No holdout evaluation available"}>
              {run.confidence === "validated" && <p className="mb-3 text-sm text-ink-secondary">{run.selection_reason}</p>}
              <TableWrap>
                <thead>
                  <tr><Th>Model</Th><Th>Role</Th><Th className="text-right">MAE</Th><Th className="text-right">RMSE</Th><Th className="text-right">Test days</Th><Th>Status</Th></tr>
                </thead>
                <tbody className="divide-y divide-navy-50">
                  {run.evaluations.map((e) => (
                    <tr key={e.model_name} className={e.is_selected ? "bg-blue-50/50" : undefined}>
                      <Td className="font-medium text-navy-900">{MODEL_LABELS[e.model_name]}</Td>
                      <Td className="capitalize text-ink-secondary">{e.role}</Td>
                      <Td className="tabular text-right">{e.mae != null ? fmtNumber(e.mae, 3) : "—"}</Td>
                      <Td className="tabular text-right">{e.rmse != null ? fmtNumber(e.rmse, 3) : "—"}</Td>
                      <Td className="tabular text-right">{e.evaluated ? e.test_samples : "—"}</Td>
                      <Td>
                        {e.is_selected && <Badge tone="blue">Selected</Badge>}{" "}
                        {e.warnings.map((w, i) => <span key={i} className="block text-xs text-ink-muted">{w}</span>)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <p className="mt-3 text-xs text-ink-muted">
                <strong>MAE</strong> is the average absolute difference between actual and predicted daily demand. <strong>RMSE</strong> is the square root of the mean squared
                difference, so it penalises large misses more. Both are in units of demand per day and are computed only on holdout dates the models did not see during training.
              </p>
            </Card>

            {run.evaluations.some((e) => e.evaluated) && (
              <Card title="Actual vs predicted on holdout dates" subtitle="Solid line = selected model; dashed = other models">
                <HoldoutChart evaluations={run.evaluations} />
              </Card>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <WarningList items={run.warnings} title="Forecast warnings" />
              <WarningList items={run.limitations} tone="info" title="Limitations" />
            </div>
          </>
        )}

        <Card title="Forecast history" subtitle={`Stored forecast runs for ${productId}`}>
          {runs.error ? (
            <ErrorState error={runs.error} onRetry={runs.reload} />
          ) : runs.data?.items.length ? (
            <TableWrap>
              <thead>
                <tr><Th>Run</Th><Th>Created</Th><Th>Horizon</Th><Th>Model</Th><Th className="text-right">Total</Th><Th className="text-right">MAE</Th><Th /></tr>
              </thead>
              <tbody className="divide-y divide-navy-50">
                {runs.data.items.map((r) => (
                  <tr key={r.id}>
                    <Td>#{r.id}</Td>
                    <Td className="text-ink-secondary">{fmtDateTime(r.created_at)}</Td>
                    <Td>{r.horizon_days} days</Td>
                    <Td>{MODEL_LABELS[r.selected_model]} {r.confidence === "low" && <Badge tone="amber">Low confidence</Badge>}</Td>
                    <Td className="tabular text-right">{fmtNumber(r.total_forecast)}</Td>
                    <Td className="tabular text-right">{r.selected_mae != null ? fmtNumber(r.selected_mae, 2) : "—"}</Td>
                    <Td className="text-right">
                      <Button variant="ghost" className="py-1 text-xs" onClick={() => openRun(r.id)} disabled={run?.id === r.id}>
                        {run?.id === r.id ? "Showing" : "View"}
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          ) : (
            <EmptyState title="No forecast runs yet" description="Choose a horizon and select Generate forecast." />
          )}
        </Card>
      </div>
    </>
  );
}

export default function ForecastingPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <ForecastingInner />
    </Suspense>
  );
}
