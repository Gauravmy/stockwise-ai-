"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Field, inputClass } from "@/components/ui";
import type { InventoryInput, InventorySetting } from "@/lib/types";

const optionalNumber = (min: number, opts: { positive?: boolean } = {}) =>
  z
    .string()
    .trim()
    .refine((v) => v === "" || !Number.isNaN(Number(v)), "Enter a number")
    .refine((v) => v === "" || (opts.positive ? Number(v) > 0 : Number(v) >= min), opts.positive ? "Must be greater than 0" : `Must be at least ${min}`);

const intInRange = (min: number, max: number) =>
  z
    .string()
    .trim()
    .refine((v) => v !== "" && Number.isInteger(Number(v)), "Enter a whole number")
    .refine((v) => Number(v) >= min && Number(v) <= max, `Must be between ${min} and ${max}`);

export const inventorySchema = z
  .object({
    current_stock: z
      .string()
      .trim()
      .refine((v) => v !== "" && !Number.isNaN(Number(v)), "Enter a number")
      .refine((v) => Number(v) >= 0, "Stock cannot be negative"),
    supplier_lead_time_days: intInRange(0, 365),
    safety_method: z.enum(["days", "quantity"]),
    safety_value: optionalNumber(0),
    minimum_order_quantity: optionalNumber(0),
    order_pack_size: optionalNumber(0, { positive: true }),
    coverage_days: intInRange(1, 365),
    overstock_threshold_days: intInRange(1, 3650),
  })
  .refine((v) => v.safety_method !== "days" || v.safety_value === "" || Number(v.safety_value) <= 365, {
    message: "Safety stock days must be at most 365",
    path: ["safety_value"],
  });

export type InventoryFormValues = z.infer<typeof inventorySchema>;

export function toFormValues(s: InventorySetting | null | undefined): InventoryFormValues {
  const str = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    current_stock: str(s?.current_stock ?? 0),
    supplier_lead_time_days: str(s?.supplier_lead_time_days ?? 7),
    safety_method: s?.safety_stock_quantity != null ? "quantity" : "days",
    safety_value: s ? str(s.safety_stock_quantity ?? s.safety_stock_days) : "3",
    minimum_order_quantity: str(s?.minimum_order_quantity),
    order_pack_size: str(s?.order_pack_size),
    coverage_days: str(s?.coverage_days ?? 14),
    overstock_threshold_days: str(s?.overstock_threshold_days ?? 90),
  };
}

export function toPayload(v: InventoryFormValues): InventoryInput {
  const num = (s: string) => (s === "" ? null : Number(s));
  return {
    current_stock: Number(v.current_stock),
    supplier_lead_time_days: Number(v.supplier_lead_time_days),
    safety_stock_days: v.safety_method === "days" ? num(v.safety_value) : null,
    safety_stock_quantity: v.safety_method === "quantity" ? num(v.safety_value) : null,
    minimum_order_quantity: num(v.minimum_order_quantity),
    order_pack_size: num(v.order_pack_size),
    coverage_days: Number(v.coverage_days),
    overstock_threshold_days: Number(v.overstock_threshold_days),
  };
}

export function InventoryForm({
  productId,
  initial,
  onSubmit,
  onCancel,
}: {
  productId: string;
  initial: InventorySetting | null;
  onSubmit: (values: InventoryInput) => Promise<void>;
  onCancel: () => void;
}) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<InventoryFormValues>({ resolver: zodResolver(inventorySchema), defaultValues: toFormValues(initial) });
  const method = watch("safety_method");
  const id = (f: string) => `${productId}-${f}`;

  return (
    <form onSubmit={handleSubmit((v) => onSubmit(toPayload(v)))} className="space-y-4" noValidate aria-label={`Inventory settings for ${productId}`}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Current stock (units)" htmlFor={id("stock")} error={errors.current_stock?.message}>
          <input id={id("stock")} inputMode="decimal" className={inputClass} {...register("current_stock")} />
        </Field>
        <Field label="Supplier lead time (days)" htmlFor={id("lead")} error={errors.supplier_lead_time_days?.message} hint="0–365">
          <input id={id("lead")} inputMode="numeric" className={inputClass} {...register("supplier_lead_time_days")} />
        </Field>
        <Field
          label="Safety stock"
          htmlFor={id("safety")}
          error={errors.safety_value?.message}
          hint={method === "days" ? "Days of average forecast demand" : "Fixed number of units"}
        >
          <div className="flex gap-2">
            <select aria-label="Safety stock method" className={`${inputClass} w-28 flex-none`} {...register("safety_method")}>
              <option value="days">Days</option>
              <option value="quantity">Units</option>
            </select>
            <input id={id("safety")} inputMode="decimal" className={inputClass} placeholder="0" {...register("safety_value")} />
          </div>
        </Field>
        <Field label="Coverage period (days)" htmlFor={id("coverage")} error={errors.coverage_days?.message} hint="Demand to cover after the order arrives">
          <input id={id("coverage")} inputMode="numeric" className={inputClass} {...register("coverage_days")} />
        </Field>
        <Field label="Minimum order quantity" htmlFor={id("moq")} error={errors.minimum_order_quantity?.message} hint="Optional">
          <input id={id("moq")} inputMode="decimal" className={inputClass} {...register("minimum_order_quantity")} />
        </Field>
        <Field label="Order pack size" htmlFor={id("pack")} error={errors.order_pack_size?.message} hint="Optional; orders round up to whole packs">
          <input id={id("pack")} inputMode="decimal" className={inputClass} {...register("order_pack_size")} />
        </Field>
        <Field label="Overstock threshold (days of cover)" htmlFor={id("over")} error={errors.overstock_threshold_days?.message}>
          <input id={id("over")} inputMode="numeric" className={inputClass} {...register("overstock_threshold_days")} />
        </Field>
      </div>
      <div className="flex gap-2">
        <Button type="submit" loading={isSubmitting}>{initial ? "Save changes" : "Create settings"}</Button>
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
