"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";

import { CategoryTrendChart, RiskBarChart } from "@/components/charts";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  RiskBadge,
  Spinner,
  TableWrap,
  Td,
  Th,
  inputClass,
} from "@/components/ui";
import { api } from "@/lib/api";
import { fmtNumber, MODEL_LABELS } from "@/lib/format";
import type { InsightItem } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function ItemList({ items, empty, mode }: { items: InsightItem[]; empty: string; mode: "reorder" | "overstock" }) {
  if (!items.length) return <EmptyState title={empty} />;
  return (
    <ul className="divide-y divide-navy-50">
      {items.map((i) => (
        <li key={i.product_id} className="py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium text-navy-900">
              {i.product_id} <span className="font-normal text-ink-muted">{i.product_name}</span>
            </p>
            <div className="flex items-center gap-2">
              <RiskBadge risk={i.stockout_risk} />
              {mode === "reorder" ? (
                <span className="tabular text-sm font-semibold text-navy-900">Order {fmtNumber(i.recommended_order_quantity)}</span>
              ) : (
                <span className="tabular text-sm font-semibold text-navy-900">{i.days_of_cover === null ? "No demand" : `${fmtNumber(i.days_of_cover)} days of cover`}</span>
              )}
            </div>
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-secondary">
            {i.explanation.map((e, idx) => <li key={idx}>{e}</li>)}
          </ul>
        </li>
      ))}
    </ul>
  );
}

export default function InsightsPage() {
  const [windowDays, setWindowDays] = useState(28);
  const data = useApi(() => api.insights({ window_days: windowDays }), [windowDays]);
  const d = data.data;

  return (
    <>
      <PageHeader
        title="Insights & Reports"
        description="Demand trends from the active dataset and prioritised, explainable inventory actions from the latest forecasts."
        actions={
          <>
            <label htmlFor="window" className="text-sm text-ink-secondary">Trend window</label>
            <select id="window" className={`${inputClass} w-auto`} value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
              {[7, 14, 28, 56, 90].map((w) => <option key={w} value={w}>{w} days</option>)}
            </select>
          </>
        }
      />
      {data.error && <ErrorState error={data.error} onRetry={data.reload} />}
      {data.loading && !d && <Spinner />}
      {d && !d.trends.length && <EmptyState title="No data yet" description="Load a dataset to see insights." />}
      {d && d.trends.length > 0 && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2" title="Monthly demand by category" subtitle="Units sold per calendar month (the first and last months may be partial)">
              <CategoryTrendChart data={d.monthly_by_category} categories={d.categories} />
            </Card>
            <Card title="Stockout-risk summary">
              <RiskBarChart counts={d.risk_counts} />
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Demand trends" subtitle={`Last ${d.window_days} days vs the previous ${d.window_days} days of history`}>
              <TableWrap>
                <thead><tr><Th>Product</Th><Th className="text-right">Recent</Th><Th className="text-right">Prior</Th><Th className="text-right">Change</Th><Th className="text-right">Avg/day</Th></tr></thead>
                <tbody className="divide-y divide-navy-50">
                  {[...d.trends].sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity)).map((t) => (
                    <tr key={t.product_id}>
                      <Td><p className="font-medium text-navy-900">{t.product_id}</p><p className="text-xs text-ink-muted">{t.product_name}</p></Td>
                      <Td className="tabular text-right">{fmtNumber(t.recent_total)}</Td>
                      <Td className="tabular text-right">{t.prior_total === null ? "—" : fmtNumber(t.prior_total)}</Td>
                      <Td className="tabular text-right">
                        {t.change_pct === null ? (
                          <span className="text-xs text-ink-muted">Not enough history</span>
                        ) : (
                          <span className={`inline-flex items-center gap-1 ${t.change_pct >= 0 ? "text-[#006300]" : "text-red-700"}`}>
                            {t.change_pct >= 0 ? <TrendingUp className="h-3.5 w-3.5" aria-hidden /> : <TrendingDown className="h-3.5 w-3.5" aria-hidden />}
                            {t.change_pct > 0 ? "+" : ""}{fmtNumber(t.change_pct, 1)}%
                          </span>
                        )}
                      </Td>
                      <Td className="tabular text-right">{fmtNumber(t.recent_avg_daily, 1)}</Td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </Card>
            <Card title="Highest forecast demand" subtitle="Average daily demand from each product's latest forecast">
              {d.top_forecast.length ? (
                <TableWrap>
                  <thead><tr><Th>Product</Th><Th className="text-right">Avg/day</Th><Th className="text-right">Total</Th><Th>Model</Th></tr></thead>
                  <tbody className="divide-y divide-navy-50">
                    {d.top_forecast.map((t) => (
                      <tr key={t.product_id}>
                        <Td><p className="font-medium text-navy-900">{t.product_id}</p><p className="text-xs text-ink-muted">{t.product_name}</p></Td>
                        <Td className="tabular text-right font-medium">{fmtNumber(t.avg_daily_forecast, 1)}</Td>
                        <Td className="tabular text-right">{fmtNumber(t.total_forecast)} <span className="text-xs text-ink-muted">/ {t.horizon_days} d</span></Td>
                        <Td className="text-xs">{MODEL_LABELS[t.selected_model]} {t.confidence === "low" && <Badge tone="amber">Low confidence</Badge>}</Td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <EmptyState title="No forecasts yet" description="Generate forecasts on the Demand Forecasting page." />
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Reorder priorities" subtitle="Ordered by stockout risk, then days until stockout">
              <ItemList items={d.reorder_priorities} empty="No reorders recommended" mode="reorder" />
            </Card>
            <Card title="Potential overstock" subtitle="Stock cover above each product's overstock threshold">
              <ItemList items={d.overstock} empty="No potential overstock detected" mode="overstock" />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
