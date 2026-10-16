// Centralised, typed client for the StockWise AI REST API.
// Errors are surfaced as ApiError; there is deliberately no fallback to fake data.

import type {
  BatchForecastResponse,
  DashboardSummary,
  DatasetDetail,
  DatasetSummary,
  ForecastRunDetail,
  ForecastRunSummary,
  InventoryInput,
  InventorySetting,
  Insights,
  Page,
  ProductDetail,
  ProductSummary,
  Recommendation,
  UploadResponse,
  ValidationReport,
} from "./types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function request<T>(path: string, init: RequestInit & { query?: Query } = {}): Promise<T> {
  const { query, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), { cache: "no-store", ...rest });
  } catch {
    throw new ApiError(
      `Cannot reach the StockWise API at ${API_BASE_URL}. Make sure the backend is running ` +
        "(a free hosted instance can take up to a minute to wake up; retry shortly).",
      0,
      "network_error",
    );
  }
  if (!res.ok) {
    let body: { error?: { message?: string; code?: string; details?: unknown; request_id?: string } } = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body */
    }
    const err = body.error;
    throw new ApiError(
      err?.message || `Request failed with status ${res.status}.`,
      res.status,
      err?.code || "http_error",
      err?.details,
      err?.request_id,
    );
  }
  return (await res.json()) as T;
}

function json<T>(method: string, path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function upload<T>(path: string, file: File, query?: Query): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return request<T>(path, { method: "POST", body: form, query });
}

export type DuplicatePolicy = "exclude" | "keep";

export const api = {
  health: () => request<{ status: string; database: string; version: string }>("/health"),

  // Products
  listProducts: (q: { search?: string; category?: string; limit?: number; offset?: number } = {}) =>
    request<Page<ProductSummary>>("/api/v1/products", { query: { limit: 500, ...q } }),
  listCategories: () => request<string[]>("/api/v1/products/categories"),
  getProduct: (productId: string, q: { start_date?: string; end_date?: string } = {}) =>
    request<ProductDetail>(`/api/v1/products/${encodeURIComponent(productId)}`, { query: q }),

  // Datasets
  validateDataset: (file: File, duplicate_policy: DuplicatePolicy) =>
    upload<{ report: ValidationReport }>("/api/v1/datasets/validate", file, { duplicate_policy }),
  uploadDataset: (file: File, duplicate_policy: DuplicatePolicy) =>
    upload<UploadResponse>("/api/v1/datasets/upload", file, { duplicate_policy }),
  loadSample: () => request<UploadResponse>("/api/v1/datasets/sample/load", { method: "POST" }),
  sampleUrl: () => buildUrl("/api/v1/datasets/sample"),
  listDatasets: (q: { limit?: number; offset?: number } = {}) =>
    request<Page<DatasetSummary>>("/api/v1/datasets", { query: q }),
  getDataset: (id: number) => request<DatasetDetail>(`/api/v1/datasets/${id}`),
  activateDataset: (id: number) =>
    request<DatasetSummary>(`/api/v1/datasets/${id}/activate`, { method: "POST" }),

  // Forecasts
  createForecast: (product_id: string, horizon_days: number) =>
    json<ForecastRunDetail>("POST", "/api/v1/forecasts", { product_id, horizon_days }),
  batchForecast: (horizon_days: number, product_ids?: string[]) =>
    json<BatchForecastResponse>("POST", "/api/v1/forecasts/batch", { horizon_days, product_ids }),
  listForecasts: (q: { product_id?: string; limit?: number; offset?: number } = {}) =>
    request<Page<ForecastRunSummary>>("/api/v1/forecasts", { query: q }),
  getForecast: (id: number) => request<ForecastRunDetail>(`/api/v1/forecasts/${id}`),

  // Inventory
  listInventory: () => request<InventorySetting[]>("/api/v1/inventory"),
  createInventory: (product_id: string, values: InventoryInput) =>
    json<InventorySetting>("POST", "/api/v1/inventory", { product_id, ...values }),
  updateInventory: (product_id: string, values: InventoryInput) =>
    json<InventorySetting>("PUT", `/api/v1/inventory/${encodeURIComponent(product_id)}`, values),
  recommendations: (q: { risk?: string; reorder_only?: boolean } = {}) =>
    request<Recommendation[]>("/api/v1/inventory/recommendations", { query: q }),

  // Analytics
  dashboard: (q: { period_days?: number; history_days?: number; category?: string } = {}) =>
    request<DashboardSummary>("/api/v1/dashboard/summary", { query: q }),
  insights: (q: { window_days?: number } = {}) => request<Insights>("/api/v1/insights", { query: q }),
};
