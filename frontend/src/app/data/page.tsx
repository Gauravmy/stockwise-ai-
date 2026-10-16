"use client";

import { Download, FileCheck2, Upload } from "lucide-react";
import { Fragment, useRef, useState } from "react";

import { ValidationReportView } from "@/components/ValidationReportView";
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
  inputClass,
} from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { ApiError, api, type DuplicatePolicy } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtNumber } from "@/lib/format";
import type { ValidationReport } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const MAX_MB = 5;

export default function DataPage() {
  const notify = useToast();
  const datasets = useApi(() => api.listDatasets({ limit: 50 }), []);
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [policy, setPolicy] = useState<DuplicatePolicy>("exclude");
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [uploadError, setUploadError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<"validate" | "import" | "sample" | "forecast" | null>(null);
  const [lastImported, setLastImported] = useState<number | null>(null);
  const [openReport, setOpenReport] = useState<{ id: number; report: ValidationReport } | null>(null);

  function pick(f: File | null) {
    setFile(f);
    setReport(null);
    setUploadError(null);
    setLastImported(null);
    if (f && !f.name.toLowerCase().endsWith(".csv")) setUploadError(new ApiError("Only .csv files are supported.", 415, "unsupported_media_type"));
    else if (f && f.size > MAX_MB * 1024 * 1024) setUploadError(new ApiError(`File exceeds the ${MAX_MB} MB limit.`, 413, "payload_too_large"));
  }

  async function validate() {
    if (!file) return;
    setBusy("validate");
    setUploadError(null);
    try {
      const res = await api.validateDataset(file, policy);
      setReport(res.report);
    } catch (e) {
      setReport(null);
      setUploadError(e as ApiError);
    } finally {
      setBusy(null);
    }
  }

  async function commit() {
    if (!file) return;
    setBusy("import");
    try {
      const res = await api.uploadDataset(file, policy);
      setReport(res.report);
      setLastImported(res.dataset.id);
      notify("success", `Imported ${res.dataset.filename} as dataset #${res.dataset.id}; it is now the active dataset.`);
      await datasets.reload();
    } catch (e) {
      setUploadError(e as ApiError);
      notify("error", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function loadSample() {
    setBusy("sample");
    try {
      const res = await api.loadSample();
      setLastImported(res.dataset.id);
      setReport(res.report);
      setFile(null);
      notify("success", `Loaded the synthetic sample as dataset #${res.dataset.id}.`);
      await datasets.reload();
    } catch (e) {
      setUploadError(e as ApiError);
      notify("error", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function forecastAll() {
    setBusy("forecast");
    try {
      const res = await api.batchForecast(60);
      notify(
        res.failed.length ? "error" : "success",
        `Generated ${res.created.length} 60-day forecast(s).${res.failed.length ? ` Failed: ${res.failed.map((f) => `${f.product_id} — ${f.message}`).join("; ")}` : ""}`,
      );
    } catch (e) {
      notify("error", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function activate(id: number) {
    try {
      await api.activateDataset(id);
      notify("success", `Dataset #${id} is now active.`);
      await datasets.reload();
    } catch (e) {
      notify("error", (e as Error).message);
    }
  }

  async function toggleReport(id: number) {
    if (openReport?.id === id) return setOpenReport(null);
    try {
      const d = await api.getDataset(id);
      setOpenReport({ id, report: d.validation_report });
    } catch (e) {
      notify("error", (e as Error).message);
    }
  }

  const duplicateId = uploadError?.code === "duplicate_import" ? (uploadError.details as { dataset_id?: number })?.dataset_id : undefined;

  return (
    <>
      <PageHeader
        title="Data Management"
        description="Upload historical sales as CSV. Files are validated first so you can review the data-quality report before anything is stored."
        actions={
          <>
            <a href={api.sampleUrl()} className="inline-flex items-center gap-1.5 rounded-md border border-navy-200 bg-white px-3 py-2 text-sm font-medium text-navy-800 hover:bg-navy-50" download>
              <Download className="h-4 w-4" aria-hidden /> Sample CSV
            </a>
            <Button variant="secondary" onClick={loadSample} loading={busy === "sample"}>Load sample dataset</Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Upload sales CSV" className="lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
            <Field label="CSV file" htmlFor="csv" hint={`Max ${MAX_MB} MB / 200,000 rows. UTF-8, comma-separated.`}>
              <input
                ref={fileInput}
                id="csv"
                type="file"
                accept=".csv,text/csv"
                className="block w-full text-sm text-ink-secondary file:mr-3 file:rounded-md file:border-0 file:bg-navy-800 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-navy-900"
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            </Field>
            <Field label="Exact duplicate rows" htmlFor="policy">
              <select id="policy" className={inputClass} value={policy} onChange={(e) => { setPolicy(e.target.value as DuplicatePolicy); setReport(null); }}>
                <option value="exclude">Exclude (default)</option>
                <option value="keep">Keep as transactions</option>
              </select>
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={validate} disabled={!file || Boolean(uploadError && uploadError.status >= 413 && uploadError.status <= 415)} loading={busy === "validate"}>
              <FileCheck2 className="h-4 w-4" aria-hidden /> Validate &amp; preview
            </Button>
            <Button onClick={commit} disabled={!file || !report?.is_valid || lastImported !== null} loading={busy === "import"}>
              <Upload className="h-4 w-4" aria-hidden /> Import dataset
            </Button>
            {lastImported !== null && (
              <Button variant="secondary" onClick={forecastAll} loading={busy === "forecast"}>Generate forecasts for all products</Button>
            )}
          </div>
          {uploadError && (
            <div className="mt-4 space-y-2">
              <ErrorState error={uploadError} />
              {uploadError.code === "missing_required_columns" && (
                <Alert tone="info">
                  Found columns: {((uploadError.details as { found_columns?: string[] })?.found_columns ?? []).join(", ") || "none"}. Required: date, product_id, quantity.
                </Alert>
              )}
              {duplicateId && (
                <Button variant="secondary" onClick={() => activate(duplicateId)}>Activate existing dataset #{duplicateId}</Button>
              )}
            </div>
          )}
        </Card>

        <Card title="CSV format">
          <ul className="space-y-1 text-sm text-ink-secondary">
            <li><strong className="text-navy-900">Required:</strong> <code>date</code> (YYYY-MM-DD), <code>product_id</code>, <code>quantity</code> (≥ 0)</li>
            <li><strong className="text-navy-900">Optional:</strong> <code>product_name</code>, <code>category</code>, <code>unit_price</code></li>
            <li>Headers such as “Date”, “Product ID” or “Quantity Sold” are recognised.</li>
            <li>Several rows for the same product and date are summed into one daily total.</li>
            <li>Dates with no rows are reported; forecasting treats them as zero-sales days.</li>
            <li>Each import becomes a new dataset version and the active one; re-uploading an identical file is rejected.</li>
          </ul>
        </Card>
      </div>

      {report && (
        <Card className="mt-4" title={lastImported ? `Validation report — dataset #${lastImported}` : "Validation report (not yet imported)"} subtitle={report.filename}>
          <ValidationReportView report={report} />
        </Card>
      )}

      <Card className="mt-4" title="Dataset history" subtitle="Every import is stored as a separate version. Forecasts and recommendations use the active dataset.">
        {datasets.error && <ErrorState error={datasets.error} onRetry={datasets.reload} />}
        {datasets.loading && !datasets.data && <Spinner />}
        {datasets.data && datasets.data.items.length === 0 && <EmptyState title="No datasets yet" description="Upload a CSV or load the synthetic sample dataset." />}
        {datasets.data && datasets.data.items.length > 0 && (
          <TableWrap>
            <thead>
              <tr><Th>ID</Th><Th>File</Th><Th className="text-right">Rows</Th><Th className="text-right">Accepted</Th><Th className="text-right">Rejected</Th><Th className="text-right">Duplicates</Th><Th className="text-right">Products</Th><Th>Date range</Th><Th>Imported</Th><Th /></tr>
            </thead>
            <tbody className="divide-y divide-navy-50">
              {datasets.data.items.map((d) => (
                <Fragment key={d.id}>
                  <tr>
                    <Td className="tabular">#{d.id}</Td>
                    <Td>
                      <span className="font-medium text-navy-900">{d.filename}</span>{" "}
                      {d.is_active && <Badge tone="green">Active</Badge>} {d.is_synthetic && <Badge>Synthetic</Badge>}
                    </Td>
                    <Td className="tabular text-right">{fmtNumber(d.total_rows)}</Td>
                    <Td className="tabular text-right">{fmtNumber(d.accepted_rows)}</Td>
                    <Td className="tabular text-right">{fmtNumber(d.rejected_rows)}</Td>
                    <Td className="tabular text-right">{fmtNumber(d.duplicate_rows)}</Td>
                    <Td className="tabular text-right">{d.product_count}</Td>
                    <Td className="whitespace-nowrap">{fmtDate(d.date_start)} – {fmtDate(d.date_end)}</Td>
                    <Td className="whitespace-nowrap text-ink-secondary">{fmtDateTime(d.created_at)}</Td>
                    <Td className="whitespace-nowrap text-right">
                      <Button variant="ghost" className="py-1 text-xs" onClick={() => toggleReport(d.id)}>{openReport?.id === d.id ? "Hide report" : "Report"}</Button>
                      {!d.is_active && <Button variant="ghost" className="py-1 text-xs" onClick={() => activate(d.id)}>Activate</Button>}
                    </Td>
                  </tr>
                  {openReport?.id === d.id && (
                    <tr><td colSpan={10} className="bg-navy-50/40 px-4 py-4"><ValidationReportView report={openReport.report} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>
    </>
  );
}
