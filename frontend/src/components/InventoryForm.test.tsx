import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InventoryForm, toPayload } from "./InventoryForm";

describe("InventoryForm", () => {
  it("blocks negative stock and shows an actionable message", async () => {
    const onSubmit = vi.fn();
    render(<InventoryForm productId="P1" initial={null} onSubmit={onSubmit} onCancel={() => {}} />);
    const stock = screen.getByLabelText("Current stock (units)");
    await userEvent.clear(stock);
    await userEvent.type(stock, "-5");
    await userEvent.click(screen.getByRole("button", { name: "Create settings" }));
    expect(await screen.findByText("Stock cannot be negative")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects a zero pack size and a fractional lead time", async () => {
    const onSubmit = vi.fn();
    render(<InventoryForm productId="P1" initial={null} onSubmit={onSubmit} onCancel={() => {}} />);
    await userEvent.type(screen.getByLabelText("Order pack size"), "0");
    const lead = screen.getByLabelText("Supplier lead time (days)");
    await userEvent.clear(lead);
    await userEvent.type(lead, "2.5");
    await userEvent.click(screen.getByRole("button", { name: "Create settings" }));
    expect(await screen.findByText("Must be greater than 0")).toBeInTheDocument();
    expect(screen.getByText("Enter a whole number")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a typed payload with one safety-stock method", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<InventoryForm productId="P1" initial={null} onSubmit={onSubmit} onCancel={() => {}} />);
    const stock = screen.getByLabelText("Current stock (units)");
    await userEvent.clear(stock);
    await userEvent.type(stock, "120");
    await userEvent.selectOptions(screen.getByLabelText("Safety stock method"), "quantity");
    const safety = screen.getByLabelText("Safety stock");
    await userEvent.clear(safety);
    await userEvent.type(safety, "25");
    await userEvent.click(screen.getByRole("button", { name: "Create settings" }));
    expect(onSubmit).toHaveBeenCalledWith({
      current_stock: 120,
      supplier_lead_time_days: 7,
      safety_stock_days: null,
      safety_stock_quantity: 25,
      minimum_order_quantity: null,
      order_pack_size: null,
      coverage_days: 14,
      overstock_threshold_days: 90,
    });
  });
});

describe("toPayload", () => {
  it("maps empty optional fields to null", () => {
    expect(
      toPayload({
        current_stock: "0",
        supplier_lead_time_days: "0",
        safety_method: "days",
        safety_value: "",
        minimum_order_quantity: "",
        order_pack_size: "12",
        coverage_days: "7",
        overstock_threshold_days: "60",
      }),
    ).toMatchObject({ safety_stock_days: null, safety_stock_quantity: null, order_pack_size: 12, minimum_order_quantity: null });
  });
});
