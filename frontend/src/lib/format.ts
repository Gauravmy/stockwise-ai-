import type { ModelName, Risk } from "./types";

export function fmtNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  // Plain YYYY-MM-DD dates are calendar dates: format without timezone shifts.
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function fmtShortDate(value: string): string {
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

export const MODEL_LABELS: Record<ModelName, string> = {
  moving_average: "Moving average (baseline)",
  seasonal_naive: "Seasonal naive (weekly)",
  random_forest: "Random forest (lag features)",
};

export const RISK_LABELS: Record<Risk, string> = {
  critical: "Critical",
  high: "High",
  moderate: "Moderate",
  low: "Low",
};

export const RISK_DESCRIPTIONS: Record<Risk, string> = {
  critical: "No stock, or stock runs out before a new order could arrive (within lead time).",
  high: "Stock is at or below the reorder point; safety stock is being consumed.",
  moderate: "Stock will reach the reorder point within about 7 days.",
  low: "Stock comfortably above the reorder point, or no forecast demand.",
};
