"use client";

import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, LineChart, Pencil, RefreshCw } from "lucide-react";
import Link from "next/link";
import { Fragment, useMemo, useState } from "react";

import { InventoryForm } from "@/components/InventoryForm";
import {
  Alert,
  Badge,
  Button,
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
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import { fmtNumber, MODEL_LABELS, RISK_DESCRIPTIONS, RISK_LABELS } from "@/lib/format";
import type { InventoryInput, Recommendation, Risk } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type SortKey = "product" | "stock" | "lead" | "rop" | "demand" | "qty" | "risk";
const RISK_RANK: Record<Risk, number> = { critical: 0, high: 1, moderate: 2, low: 3 };

function sortValue(r: Recommendation, key: SortKey): number | string {
  const rec = r.recommendation;
  switch (key) {
    case "product":
      return r.product_id;
    case "stock":
      return r.inventory?.current_stock ?? -1;
    case "lead":
      return r.inventory?.supplier_lead_time_days ?? -1;
    case "rop":
      return rec?.reorder_point ?? -1;
    case "demand":
      return rec?.protection_period_demand ?? -1;
    case "qty":
      return rec?.recommended_order_quantity ?? -1;
    case "risk":
      return rec ? RISK_RANK[rec.stockout_risk] : 9;
  }
}

export default function InventoryPage() {
  const notify = useToast();
  const recs = useApi(() => api.recommendations(), []);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<"" | Risk | "reorder" | "overstock">("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "risk", dir: 1 });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [batching, setBatching] = useState(false);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (recs.data ?? [])
      .filter((r) => !q || r.product_id.toLowerCase().includes(q) || (r.product_name ?? "").toLowerCase().includes(q))
      .filter((r) => {
        if (!riskFilter) return true;
        const rec = r.recommendation;
        if (!rec) return false;
        if (riskFilter === "reorder") return rec.reorder_needed;
        if (riskFilter === "overstock") return rec.overstock;
        return rec.stockout_risk === riskFilter;
      })
      .sort((a, b) => {
        const va = sortValue(a, sort.key);
        const vb = sortValue(b, sort.key);
        const cmp = typeof va === "string" ? va.localeCompare(String(vb)) : va - (vb as number);
        return cmp * sort.dir || a.product_id.localeCompare(b.product_id);
      });
  }, [recs.data, search, riskFilter, sort]);

  const missingForecasts = (recs.data ?? []).filter((r) => r.status === "no_forecast").map((r) => r.product_id);

  async function save(r: Recommendation, values: InventoryInput) {
    try {
      if (r.inventory) await api.updateInventory(r.product_id, values);
      else await api.createInventory(r.product_id, values);
      notify("success", `Inventory settings saved for ${r.product_id}.`);
      setEditing(null);
      setExpanded(r.product_id);
      await recs.reload();
    } catch (e) {
      notify("error", (e as Error).message);
    }
  }

  async function forecastMissing() {
    setBatching(true);
    try {
      const res = await api.batchForecast(60, missingForecasts);
      notify(res.failed.length ? "error" : "success", `Created ${res.created.length} forecast(s)${res.failed.length ? `; ${res.failed.length} failed: ${res.failed.map((f) => `${f.product_id} (${f.message})`).join("; ")}` : ""}.`);
      await recs.reload();
    } catch (e) {
      notify("error", (e as Error).message);
    } finally {
      setBatching(false);
    }
  }

  function SortTh({ k, children, right }: { k: SortKey; children: React.ReactNode; right?: boolean }) {
    const active = sort.key === k;
    return (
      <Th className={right ? "text-right" : undefined} aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button
          className={`inline-flex items-center gap-1 uppercase ${active ? "text-navy-900" : ""}`}
          onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? (s.dir === 1 ? -1 : 1) : 1 }))}
        >
          {children}
          {active && (sort.dir === 1 ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />)}
        </button>
      </Th>
    );
  }

  return (
    <>
      <PageHeader
        title="Inventory Management"
        description="Configure stock and supplier lead times. Recommendations use the latest forecast for each product and a transparent reorder-point / order-up-to policy."
        actions={
          <>
            {missingForecasts.length > 0 && (
              <Button variant="secondary" onClick={forecastMissing} loading={batching}>
                <LineChart className="h-4 w-4" aria-hidden /> Forecast {missingForecasts.length} missing
              </Button>
            )}
            <Button variant="secondary" onClick={() => recs.reload()} disabled={recs.loading}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
            </Button>
          </>
        }
      />

      <Card className="mb-4" bodyClassName="p-0">
        <details className="group px-4 py-3 text-sm text-ink-secondary">
          <summary className="cursor-pointer font-medium text-navy-900">How recommendations are calculated</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li><strong>Lead-time demand</strong> = sum of forecast daily demand over the supplier lead time.</li>
            <li><strong>Safety stock</strong> = a fixed quantity, or average forecast daily demand × safety-stock days (a heuristic, not a guaranteed service level).</li>
            <li><strong>Reorder point</strong> = lead-time demand + safety stock. A reorder is recommended when current stock ≤ reorder point.</li>
            <li><strong>Target stock</strong> = forecast demand over (lead time + coverage days) + safety stock. Order quantity = target − current stock, raised to the minimum order quantity and rounded up to whole packs.</li>
            {(Object.keys(RISK_LABELS) as Risk[]).map((r) => (
              <li key={r}><strong>{RISK_LABELS[r]} risk</strong>: {RISK_DESCRIPTIONS[r]}</li>
            ))}
            <li><strong>Potential overstock</strong>: stock covers more days of average forecast demand than the configured threshold, or stock is held with no forecast demand.</li>
          </ul>
        </details>
      </Card>

      <Card>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row">
          <label htmlFor="inv-search" className="sr-only">Search products</label>
          <input id="inv-search" className={`${inputClass} sm:max-w-xs`} placeholder="Search by product ID or name" value={search} onChange={(e) => setSearch(e.target.value)} />
          <label htmlFor="inv-filter" className="sr-only">Filter</label>
          <select id="inv-filter" className={`${inputClass} sm:w-48`} value={riskFilter} onChange={(e) => setRiskFilter(e.target.value as typeof riskFilter)}>
            <option value="">All products</option>
            <option value="reorder">Reorder recommended</option>
            <option value="overstock">Potential overstock</option>
            {(Object.keys(RISK_LABELS) as Risk[]).map((r) => <option key={r} value={r}>{RISK_LABELS[r]} risk</option>)}
          </select>
        </div>

        {recs.error && <ErrorState error={recs.error} onRetry={recs.reload} />}
        {recs.loading && !recs.data && <Spinner />}
        {recs.data && recs.data.length === 0 && (
          <EmptyState title="No products in the active dataset" description="Load or upload sales data on the Data Management page." />
        )}
        {recs.data && recs.data.length > 0 && rows.length === 0 && <EmptyState title="No products match the current filters" />}

        {rows.length > 0 && (
          <TableWrap>
            <thead>
              <tr>
                <Th><span className="sr-only">Expand</span></Th>
                <SortTh k="product">Product</SortTh>
                <SortTh k="stock" right>Stock</SortTh>
                <SortTh k="lead" right>Lead time</SortTh>
                <Th className="text-right">Safety stock</Th>
                <SortTh k="rop" right>Reorder point</SortTh>
                <SortTh k="demand" right>Demand (lead + cover)</SortTh>
                <SortTh k="qty" right>Order qty</SortTh>
                <SortTh k="risk">Risk</SortTh>
                <Th><span className="sr-only">Actions</span></Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-50">
              {rows.map((r) => {
                const rec = r.recommendation;
                const open = expanded === r.product_id || editing === r.product_id;
                return (
                  <Fragment key={r.product_id}>
                    <tr className={open ? "bg-navy-50/50" : undefined}>
                      <Td>
                        <button
                          aria-label={open ? `Hide details for ${r.product_id}` : `Show details for ${r.product_id}`}
                          aria-expanded={open}
                          onClick={() => {
                            setExpanded(open ? null : r.product_id);
                            if (open) setEditing(null);
                          }}
                          className="rounded p-0.5 text-ink-muted hover:bg-navy-100"
                        >
                          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                      </Td>
                      <Td>
                        <p className="font-medium text-navy-900">{r.product_id}</p>
                        <p className="text-xs text-ink-muted">{r.product_name}</p>
                      </Td>
                      <Td className="tabular text-right">{r.inventory ? fmtNumber(r.inventory.current_stock) : "—"}</Td>
                      <Td className="tabular text-right">{r.inventory ? `${r.inventory.supplier_lead_time_days} d` : "—"}</Td>
                      <Td className="tabular text-right">{rec ? fmtNumber(rec.safety_stock) : "—"}</Td>
                      <Td className="tabular text-right">{rec ? fmtNumber(rec.reorder_point) : "—"}</Td>
                      <Td className="tabular text-right" title={rec ? `Over lead time + coverage (${rec.protection_period_days} days)` : undefined}>
                        {rec ? fmtNumber(rec.protection_period_demand) : "—"}
                      </Td>
                      <Td className="tabular text-right font-semibold text-navy-900">{rec ? fmtNumber(rec.recommended_order_quantity) : "—"}</Td>
                      <Td>
                        {rec ? (
                          <div className="flex flex-wrap gap-1">
                            <RiskBadge risk={rec.stockout_risk} />
                            {rec.overstock && <Badge tone="amber">Overstock</Badge>}
                          </div>
                        ) : r.status === "not_configured" ? (
                          <Badge>Not configured</Badge>
                        ) : (
                          <Badge tone="amber">No forecast</Badge>
                        )}
                      </Td>
                      <Td>
                        <Button
                          variant="ghost"
                          className="py-1 text-xs"
                          onClick={() => {
                            setEditing(r.product_id);
                            setExpanded(r.product_id);
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5" aria-hidden /> {r.inventory ? "Edit" : "Configure"}
                        </Button>
                      </Td>
                    </tr>
                    {open && (
                      <tr className="bg-navy-50/50">
                        <td colSpan={10} className="px-4 pb-4 pt-1">
                          {editing === r.product_id ? (
                            <InventoryForm productId={r.product_id} initial={r.inventory} onSubmit={(v) => save(r, v)} onCancel={() => setEditing(null)} />
                          ) : rec ? (
                            <div className="grid gap-4 lg:grid-cols-3">
                              <div className="lg:col-span-2">
                                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Explanation</p>
                                <ul className="list-disc space-y-1 pl-5 text-sm text-ink-secondary">
                                  {rec.explanation.map((e, i) => <li key={i}>{e}</li>)}
                                </ul>
                                {rec.warnings.length > 0 && (
                                  <div className="mt-2"><Alert tone="warning">{rec.warnings.join(" ")}</Alert></div>
                                )}
                              </div>
                              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                                {[
                                  ["Avg forecast / day", fmtNumber(rec.avg_daily_forecast, 2)],
                                  ["Lead-time demand", fmtNumber(rec.lead_time_demand, 1)],
                                  ["Safety stock", `${fmtNumber(rec.safety_stock, 1)} (${rec.safety_stock_method})`],
                                  ["Reorder point", fmtNumber(rec.reorder_point, 1)],
                                  ["Target stock", fmtNumber(rec.target_stock, 1)],
                                  ["Order-up-to gap", fmtNumber(rec.order_up_to_gap, 1)],
                                  ["Days until stockout", rec.days_until_stockout === null ? `Not within ${r.forecast_horizon_days} days` : fmtNumber(rec.days_until_stockout, 1)],
                                  ["Days of cover", rec.days_of_cover === null ? "—" : fmtNumber(rec.days_of_cover, 0)],
                                  ["Forecast", `#${r.forecast_run_id}, ${r.forecast_horizon_days} d, ${r.forecast_selected_model ? MODEL_LABELS[r.forecast_selected_model] : ""}`],
                                ].map(([k, v]) => (
                                  <Fragment key={k}>
                                    <dt className="text-ink-muted">{k}</dt>
                                    <dd className="tabular text-right font-medium text-navy-900">{v}</dd>
                                  </Fragment>
                                ))}
                              </dl>
                              <Link href={`/forecasting?product=${encodeURIComponent(r.product_id)}`} className="text-sm font-medium text-accent hover:underline">
                                View forecast for {r.product_id} →
                              </Link>
                            </div>
                          ) : (
                            <p className="text-sm text-ink-secondary">{r.message}</p>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </TableWrap>
        )}
      </Card>
    </>
  );
}
