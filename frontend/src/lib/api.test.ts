import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("builds query strings and skips empty values", async () => {
    const fetchFn = mockFetch(() => ok({ items: [], total: 0, limit: 500, offset: 0 }));
    await api.listProducts({ search: "tea", category: "" });
    const url = new URL(fetchFn.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/v1/products");
    expect(url.searchParams.get("search")).toBe("tea");
    expect(url.searchParams.has("category")).toBe(false);
    expect(url.searchParams.get("limit")).toBe("500");
  });

  it("raises ApiError with the structured backend error", async () => {
    mockFetch(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ error: { code: "insufficient_history", message: "Need 14 days", details: null, request_id: "abc" } }),
          { status: 422 },
        ),
      ),
    );
    const err = await api.createForecast("P1", 30).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("insufficient_history");
    expect(err.message).toBe("Need 14 days");
    expect(err.requestId).toBe("abc");
  });

  it("reports an unreachable backend instead of returning fake data", async () => {
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const err = await api.dashboard().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network_error");
    expect(err.message).toMatch(/Cannot reach the StockWise API/);
  });

  it("sends JSON bodies for forecasts and inventory updates", async () => {
    const fetchFn = mockFetch(() => ok({}));
    await api.createForecast("SKU 1", 14);
    const [, init] = fetchFn.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ product_id: "SKU 1", horizon_days: 14 });

    await api.updateInventory("SKU 1", {
      current_stock: 1, supplier_lead_time_days: 2, safety_stock_days: null, safety_stock_quantity: 3,
      minimum_order_quantity: null, order_pack_size: null, coverage_days: 14, overstock_threshold_days: 90,
    });
    const [url2, init2] = fetchFn.mock.calls[1];
    expect(url2).toContain("/api/v1/inventory/SKU%201");
    expect(init2?.method).toBe("PUT");
  });

  it("uploads CSV files as multipart form data with the duplicate policy", async () => {
    const fetchFn = mockFetch(() => ok({ report: {} }));
    const file = new File(["date,product_id,quantity\n"], "s.csv", { type: "text/csv" });
    await api.validateDataset(file, "keep");
    const [url, init] = fetchFn.mock.calls[0];
    expect(new URL(url).searchParams.get("duplicate_policy")).toBe("keep");
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
  });
});
