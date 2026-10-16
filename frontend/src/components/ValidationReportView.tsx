"use client";

import { Alert, Badge, TableWrap, Td, Th, WarningList } from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";
import type { ValidationReport } from "@/lib/types";

function Stat({ label, value, tone }: { label: string; value: number; tone?: "bad" | "warn" }) {
  return (
    <div className="rounded-md border border-navy-100 bg-white px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">{label}</p>
      <p className={`tabular text-lg font-semibold ${tone === "bad" && value ? "text-status-critical" : tone === "warn" && value ? "text-[#b45309]" : "text-navy-900"}`}>{fmtNumber(value)}</p>
    </div>
  );
}

export function ValidationReportView({ report }: { report: ValidationReport }) {
  const missing = Object.entries(report.missing_values).filter(([, n]) => n > 0);
  return (
    <div className="space-y-4">
      {report.is_valid ? (
        <Alert tone="success" title={`${fmtNumber(report.accepted_rows)} of ${fmtNumber(report.total_rows)} rows passed validation`}>
          {report.product_count} product(s), {fmtNumber(report.daily_records)} daily records, {fmtDate(report.date_start)} – {fmtDate(report.date_end)}.
        </Alert>
      ) : (
        <Alert tone="error" title="No rows passed validation">Fix the issues listed below and upload the file again.</Alert>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <Stat label="Total rows" value={report.total_rows} />
        <Stat label="Accepted" value={report.accepted_rows} />
        <Stat label="Rejected" value={report.rejected_rows} tone="bad" />
        <Stat label="Duplicates" value={report.duplicate_rows} tone="warn" />
        <Stat label="Aggregated" value={report.aggregated_rows} />
        <Stat label="Invalid dates" value={report.invalid_dates} tone="bad" />
        <Stat label="Invalid qty" value={report.invalid_quantities} tone="bad" />
        <Stat label="Negative qty" value={report.negative_quantities} tone="bad" />
      </div>

      <div className="text-xs text-ink-secondary">
        <span className="font-medium text-navy-900">Column mapping: </span>
        {Object.entries(report.column_mapping).map(([k, v]) => (
          <span key={k} className="mr-2 inline-block">
            <code className="rounded bg-navy-50 px-1">{v}</code> → <code className="rounded bg-navy-50 px-1">{k}</code>
          </span>
        ))}
        {missing.length > 0 && (
          <p className="mt-1">
            <span className="font-medium text-navy-900">Missing values: </span>
            {missing.map(([k, n]) => `${k}: ${n}`).join(", ")}
          </p>
        )}
        <p className="mt-1">
          <span className="font-medium text-navy-900">Duplicate policy: </span>
          {report.duplicate_policy === "exclude" ? "exact duplicate rows excluded (first kept)" : "exact duplicate rows kept and summed"}
          {report.duplicate_row_numbers.length > 0 && ` — duplicate rows: ${report.duplicate_row_numbers.slice(0, 15).join(", ")}${report.duplicate_row_numbers.length > 15 ? "…" : ""}`}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <WarningList items={report.warnings} title="Data-quality warnings" />
        <WarningList items={report.instructions} tone="info" title="How to fix" />
      </div>

      {report.rejected_samples.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-navy-900">
            Rejected rows {report.rejected_rows > report.rejected_samples.length && <span className="font-normal text-ink-muted">(first {report.rejected_samples.length} of {report.rejected_rows})</span>}
          </h3>
          <TableWrap>
            <thead><tr><Th>Line</Th><Th>Reasons</Th><Th>Values</Th></tr></thead>
            <tbody className="divide-y divide-navy-50">
              {report.rejected_samples.map((s) => (
                <tr key={s.row_number}>
                  <Td className="tabular">{s.row_number}</Td>
                  <Td>{s.reasons.map((r) => <Badge key={r} tone="amber">{r}</Badge>)}</Td>
                  <Td className="font-mono text-xs text-ink-secondary">{Object.entries(s.values).map(([k, v]) => `${k}=${v === "" ? "∅" : v}`).join("  ")}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}

      {report.products.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-navy-900">Coverage by product</h3>
          <TableWrap>
            <thead><tr><Th>Product</Th><Th>First</Th><Th>Last</Th><Th className="text-right">Span (days)</Th><Th className="text-right">Days with sales</Th><Th className="text-right">Missing dates</Th><Th className="text-right">Total qty</Th></tr></thead>
            <tbody className="divide-y divide-navy-50">
              {report.products.map((p) => (
                <tr key={p.product_id}>
                  <Td className="font-medium">{p.product_id}</Td>
                  <Td>{fmtDate(p.first_date)}</Td>
                  <Td>{fmtDate(p.last_date)}</Td>
                  <Td className="tabular text-right">{p.span_days}</Td>
                  <Td className="tabular text-right">{p.observed_days}</Td>
                  <Td className="tabular text-right">{p.missing_dates} <span className="text-ink-muted">({Math.round(p.missing_date_ratio * 100)}%)</span></Td>
                  <Td className="tabular text-right">{fmtNumber(p.total_quantity)}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}

      {report.preview.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-navy-900">Preview of accepted rows (first {report.preview.length})</h3>
          <TableWrap>
            <thead><tr><Th>Line</Th><Th>Date</Th><Th>Product</Th><Th className="text-right">Quantity</Th><Th>Name</Th><Th>Category</Th><Th className="text-right">Unit price</Th></tr></thead>
            <tbody className="divide-y divide-navy-50">
              {report.preview.map((r) => (
                <tr key={r.row_number}>
                  <Td className="tabular text-ink-muted">{r.row_number}</Td>
                  <Td>{r.date}</Td>
                  <Td>{r.product_id}</Td>
                  <Td className="tabular text-right">{fmtNumber(r.quantity, 2)}</Td>
                  <Td>{r.product_name ?? "—"}</Td>
                  <Td>{r.category ?? "—"}</Td>
                  <Td className="tabular text-right">{r.unit_price != null ? fmtNumber(r.unit_price, 2) : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </div>
  );
}
