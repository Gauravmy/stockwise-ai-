"use client";

import Link from "next/link";
import { useState } from "react";

import { DemandChart, RiskBarChart } from "@/components/charts";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  RiskBadge,
  Skeleton,
  StatCard,
  TableWrap,
  Td,
  Th,
  WarningList,
  inputClass,
} from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtNumber, MODEL_LABELS } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PERIODS = [7, 14, 30, 60];

export default function OverviewPage() {
  const notify = useToast();
  const [period, setPeriod] = useState(30);
  const [category, setCategory] = useState("");
  const [loadingSample, setLoadingSample] = useState(false);
  const summary = useApi(() => api.dashboard({ period_days: period, category: category || undefined }), [period, category]);
  const categories = useApi(() => api.listCategories(), []);

  async function loadSample() {
    setLoadingSample(true);
    try {
      const res = await api.loadSample();
      await api.batchForecast(60);
      notify("success", `Loaded synthetic sample dataset #${res.dataset.id} and generated forecasts.`);
      await Promise.all([summary.reload(), categories.reload()]);
    } catch (e) {
      notify("error", (e as Error).message);
    } finally {
      setLoadingSample(false);
    }
  }

  const d = summary.data;

  return (
    <>
      <PageHeader
        title="Overview"
        description="Stock health, forecast demand and recent activity for the active dataset."
        actions={
          <>
            <label className="sr-only" htmlFor="period">Forecast period</label>
            <select id="period" className={`${inputClass} w-auto`} value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
              {PERIODS.map((p) => (
                <option key={p} value={p}>Next {p} days</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="category">Category</label>
            <select id="category" className={`${inputClass} w-auto`} value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {categories.data?.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </>
        }
      />

      {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}

      {summary.loading && !d && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}
          <Skeleton className="h-72 sm:col-span-2 xl:col-span-4" />
        </div>
      )}

      {d && !d.active_dataset && (
        <Card>
          <EmptyState
            title="No sales data loaded yet"
            description="Upload a CSV of historical sales on the Data Management page, or load the synthetic sample dataset to explore the application."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button onClick={loadSample} loading={loadingSample}>Load sample dataset</Button>
                <Link href="/data" className="inline-flex items-center rounded-md border border-navy-200 bg-white px-3 py-2 text-sm font-medium text-navy-800 hover:bg-navy-50">
                  Upload CSV
                </Link>
              </div>
            }
          />
        </Card>
      )}

      {d && d.active_dataset && (
        <div className="space-y-4">
          {d.active_dataset.is_synthetic && (
            <Alert tone="info">
              The active dataset <strong>{d.active_dataset.filename}</strong> is <strong>synthetic sample data</strong> generated with a fixed random seed.
            </Alert>
          )}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Products" value={fmtNumber(d.total_products)} hint={`Dataset #${d.active_dataset.id} · ${fmtDate(d.active_dataset.date_start)} – ${fmtDate(d.active_dataset.date_end)}`} />
            <StatCard
              label="Products at risk"
              value={fmtNumber(d.products_at_risk)}
              tone={d.products_at_risk ? "critical" : "default"}
              hint={`${d.risk_counts.critical} critical · ${d.risk_counts.high} high`}
            />
            <StatCard
              label="Require reorder"
              value={fmtNumber(d.products_requiring_reorder)}
              tone={d.products_requiring_reorder ? "warning" : "default"}
              hint={`${d.products_overstocked} potential overstock`}
            />
            <StatCard
              label={`Forecast demand · ${d.period_days} days`}
              value={fmtNumber(d.forecast_demand)}
              hint={`units across ${d.forecast_products_covered} forecast product(s)`}
            />
          </div>

          {(d.products_not_configured > 0 || d.products_without_forecast > 0) && (
            <Alert tone="warning">
              {d.products_not_configured > 0 && <span>{d.products_not_configured} product(s) have no inventory settings. </span>}
              {d.products_without_forecast > 0 && <span>{d.products_without_forecast} configured product(s) have no forecast yet. </span>}
              <Link className="font-medium underline" href="/inventory">Review inventory</Link>
            </Alert>
          )}
          <WarningList items={d.forecast_period_warnings} tone="info" title="Forecast period coverage" />

          <div className="grid gap-4 xl:grid-cols-3">
            <Card
              className="xl:col-span-2"
              title="Historical and forecast demand"
              subtitle={`Total units per day${d.category ? ` in ${d.category}` : ""}: last 90 days of history, then the latest forecast for each product`}
            >
              {d.demand_series.length ? (
                <DemandChart data={d.demand_series} ariaLabel="Aggregated historical and forecast daily demand" />
              ) : (
                <EmptyState title="No demand data for this selection" />
              )}
            </Card>
            <Card title="Stockout risk" subtitle="Products with inventory settings and a forecast">
              <RiskBarChart counts={d.risk_counts} />
              <p className="mt-2 text-xs text-ink-muted">
                Risk levels follow documented rules based on stock, lead time and forecast demand.{" "}
                <Link href="/inventory" className="underline">See explanations</Link>
              </p>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Highest-risk products">
              {d.highest_risk.length ? (
                <TableWrap>
                  <thead>
                    <tr><Th>Product</Th><Th>Risk</Th><Th className="text-right">Stock</Th><Th className="text-right">Reorder point</Th><Th className="text-right">Days to stockout</Th><Th className="text-right">Order qty</Th></tr>
                  </thead>
                  <tbody className="divide-y divide-navy-50">
                    {d.highest_risk.map((r) => (
                      <tr key={r.product_id}>
                        <Td><p className="font-medium text-navy-900">{r.product_id}</p><p className="text-xs text-ink-muted">{r.product_name}</p></Td>
                        <Td><RiskBadge risk={r.stockout_risk} /></Td>
                        <Td className="tabular text-right">{fmtNumber(r.current_stock)}</Td>
                        <Td className="tabular text-right">{fmtNumber(r.reorder_point)}</Td>
                        <Td className="tabular text-right">{r.days_until_stockout === null ? "—" : fmtNumber(r.days_until_stockout, 1)}</Td>
                        <Td className="tabular text-right font-medium">{fmtNumber(r.recommended_order_quantity)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <EmptyState title="No products at elevated risk" description="Products appear here when their risk is moderate, high or critical." />
              )}
            </Card>
            <Card title="Data-quality warnings" subtitle={`From validation of dataset #${d.active_dataset.id}`}>
              {d.data_quality_warnings.length ? (
                <ul className="space-y-1.5 text-sm text-ink-secondary">
                  {d.data_quality_warnings.map((w, i) => <li key={i} className="border-l-2 border-amber-300 pl-2">{w}</li>)}
                </ul>
              ) : (
                <p className="text-sm text-ink-muted">No data-quality warnings were raised for this dataset.</p>
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Recent datasets" actions={<Link href="/data" className="text-xs font-medium text-accent hover:underline">Manage</Link>}>
              <ul className="divide-y divide-navy-50 text-sm">
                {d.recent_datasets.map((ds) => (
                  <li key={ds.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span className="min-w-0">
                      <span className="font-medium text-navy-900">#{ds.id} {ds.filename}</span>{" "}
                      {ds.is_active && <Badge tone="green">Active</Badge>} {ds.is_synthetic && <Badge>Synthetic</Badge>}
                    </span>
                    <span className="tabular text-xs text-ink-muted">{fmtNumber(ds.accepted_rows)} rows · {fmtDateTime(ds.created_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Recent forecast runs" actions={<Link href="/forecasting" className="text-xs font-medium text-accent hover:underline">Forecast</Link>}>
              {d.recent_forecasts.length ? (
                <ul className="divide-y divide-navy-50 text-sm">
                  {d.recent_forecasts.map((f) => (
                    <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span>
                        <span className="font-medium text-navy-900">#{f.id} {f.product_id}</span>{" "}
                        <span className="text-ink-secondary">{MODEL_LABELS[f.selected_model]}, {f.horizon_days} days</span>{" "}
                        {f.confidence === "low" && <Badge tone="amber">Low confidence</Badge>}
                      </span>
                      <span className="tabular text-xs text-ink-muted">{fmtDateTime(f.created_at)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No forecasts yet" />
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
