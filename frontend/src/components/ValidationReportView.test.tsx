import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ValidationReport } from "@/lib/types";

import { ValidationReportView } from "./ValidationReportView";

const report: ValidationReport = {
  filename: "bad.csv",
  is_valid: true,
  total_rows: 5,
  accepted_rows: 3,
  rejected_rows: 2,
  duplicate_rows: 1,
  duplicate_row_numbers: [4],
  duplicate_policy: "exclude",
  aggregated_rows: 0,
  daily_records: 3,
  product_count: 1,
  date_start: "2024-01-01",
  date_end: "2024-01-03",
  missing_values: { date: 0, product_id: 0, quantity: 1 },
  invalid_optional_values: 0,
  invalid_dates: 1,
  future_dates: 0,
  invalid_quantities: 1,
  negative_quantities: 0,
  invalid_product_ids: 0,
  column_mapping: { date: "Date", product_id: "SKU", quantity: "Qty" },
  ignored_columns: [],
  products: [],
  rejected_samples: [
    { row_number: 3, reasons: ["invalid date (expected YYYY-MM-DD)"], values: { date: "31/01/2024", product_id: "A", quantity: "2" } },
    { row_number: 6, reasons: ["missing quantity"], values: { date: "2024-01-05", product_id: "A", quantity: "" } },
  ],
  warnings: ["1 exact duplicate row(s) were excluded (first occurrence kept)."],
  instructions: ["Use ISO dates in the form YYYY-MM-DD (e.g. 2025-03-31) and remove future dates."],
  preview: [],
};

describe("ValidationReportView", () => {
  it("shows counts, rejected-row reasons and correction instructions", () => {
    render(<ValidationReportView report={report} />);
    expect(screen.getByText("3 of 5 rows passed validation")).toBeInTheDocument();
    expect(screen.getByText("invalid date (expected YYYY-MM-DD)")).toBeInTheDocument();
    expect(screen.getByText("missing quantity")).toBeInTheDocument();
    expect(screen.getByText(/Use ISO dates/)).toBeInTheDocument();
    expect(screen.getByText(/duplicate rows: 4/)).toBeInTheDocument();
    expect(screen.getByText(/quantity: 1/)).toBeInTheDocument();
  });

  it("flags a file with no valid rows", () => {
    render(<ValidationReportView report={{ ...report, is_valid: false, accepted_rows: 0 }} />);
    expect(screen.getByText("No rows passed validation")).toBeInTheDocument();
  });
});
