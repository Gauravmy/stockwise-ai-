"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Area,
  Cell,
  LabelList,
} from "recharts";

import { fmtDate, fmtNumber, fmtShortDate, MODEL_LABELS, RISK_LABELS } from "@/lib/format";
import type { ModelEvaluation, ModelName, RiskCounts } from "@/lib/types";

// Validated categorical palette (light surface), assigned in fixed order.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const GRID = "#e1e0d9";
const AXIS = "#898781";
const STATUS = { critical: "#d03b3b", high: "#ec835a", moderate: "#fab219", low: "#0ca30c" } as const;

const axisProps = {
  tick: { fill: AXIS, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: "#c3c2b7" },
} as const;

type TooltipEntry = { name?: string; value?: number | null; color?: string; dataKey?: string | number };

function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter = fmtDate,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
  labelFormatter?: (l: string) => string;
}) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((p) => p.value !== null && p.value !== undefined);
  if (!rows.length) return null;
  return (
    <div className="rounded-md border border-navy-100 bg-white px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-navy-900">{label ? labelFormatter(String(label)) : ""}</p>
      {rows.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-ink-secondary">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} aria-hidden />
          <span>{p.name}</span>
          <span className="tabular ml-auto pl-3 font-medium text-ink">{fmtNumber(p.value as number, 1)}</span>
        </p>
      ))}
    </div>
  );
}

export interface DemandPoint {
  date: string;
  actual: number | null;
  forecast: number | null;
}

/** History (solid) and forecast (dashed) with a marker at the forecast start. */
export function DemandChart({ data, height = 300, ariaLabel }: { data: DemandPoint[]; height?: number; ariaLabel: string }) {
  const firstForecast = data.find((d) => d.forecast !== null)?.date;
  return (
    <div role="img" aria-label={ariaLabel} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={fmtShortDate} minTickGap={32} {...axisProps} />
          <YAxis {...axisProps} width={48} tickFormatter={(v) => fmtNumber(v)} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#c3c2b7" }} />
          <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: "#52514e" }} />
          <Area
            type="monotone"
            dataKey="actual"
            name="Historical demand"
            stroke={SERIES[0]}
            strokeWidth={2}
            fill={SERIES[0]}
            fillOpacity={0.08}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            name="Forecast demand"
            stroke={SERIES[1]}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          {firstForecast && (
            <ReferenceLine
              x={firstForecast}
              stroke="#52514e"
              strokeDasharray="2 3"
              label={{ value: "Forecast starts", position: "insideTopLeft", fill: "#52514e", fontSize: 11 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Actual vs predicted demand on the shared chronological holdout window. */
export function HoldoutChart({ evaluations, height = 280 }: { evaluations: ModelEvaluation[]; height?: number }) {
  const evaluated = evaluations.filter((e) => e.evaluated && e.holdout.length);
  if (!evaluated.length) return null;
  const order: ModelName[] = ["moving_average", "seasonal_naive", "random_forest"];
  const models = order.filter((m) => evaluated.some((e) => e.model_name === m));
  const rows = evaluated[0].holdout.map((h, i) => {
    const row: Record<string, number | string> = { date: h.date, actual: h.actual };
    for (const e of evaluated) row[e.model_name] = e.holdout[i]?.predicted;
    return row;
  });
  return (
    <div role="img" aria-label="Actual versus predicted demand on holdout dates" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={fmtShortDate} minTickGap={24} {...axisProps} />
          <YAxis {...axisProps} width={48} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#c3c2b7" }} />
          <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: "#52514e" }} />
          <Line dataKey="actual" name="Actual" stroke={SERIES[0]} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
          {models.map((m, i) => (
            <Line
              key={m}
              dataKey={m}
              name={MODEL_LABELS[m]}
              stroke={SERIES[i + 1]}
              strokeWidth={2}
              strokeDasharray={evaluated.find((e) => e.model_name === m)?.is_selected ? undefined : "4 3"}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Monthly demand stacked by category. */
export function CategoryTrendChart({
  data,
  categories,
  height = 300,
}: {
  data: ({ month: string } & Record<string, number | string>)[];
  categories: string[];
  height?: number;
}) {
  const fmtMonth = (m: string) => {
    const [y, mo] = m.split("-").map(Number);
    return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" });
  };
  return (
    <div role="img" aria-label="Monthly demand by category" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="month" tickFormatter={fmtMonth} {...axisProps} minTickGap={8} />
          <YAxis {...axisProps} width={52} tickFormatter={(v) => fmtNumber(v)} />
          <Tooltip content={<ChartTooltip labelFormatter={fmtMonth} />} cursor={{ fill: "rgba(11,11,11,0.04)" }} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#52514e" }} iconType="square" />
          {categories.slice(0, SERIES.length).map((c, i) => (
            <Bar key={c} dataKey={c} name={c} stackId="a" fill={SERIES[i]} stroke="#fcfcfb" strokeWidth={1} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Product count per stockout-risk level (status colours + text labels). */
export function RiskBarChart({ counts, height = 180 }: { counts: RiskCounts; height?: number }) {
  const rows = (Object.keys(STATUS) as (keyof RiskCounts)[]).map((k) => ({ risk: RISK_LABELS[k], key: k, count: counts[k] }));
  return (
    <div role="img" aria-label="Products by stockout risk level" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 32, bottom: 0, left: 8 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" allowDecimals={false} {...axisProps} />
          <YAxis type="category" dataKey="risk" width={72} {...axisProps} />
          <Tooltip
            cursor={{ fill: "rgba(11,11,11,0.04)" }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <div className="rounded-md border border-navy-100 bg-white px-3 py-2 text-xs shadow-md">
                  {payload[0].payload.risk}: <span className="font-medium">{payload[0].value}</span> product(s)
                </div>
              ) : null
            }
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18} isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.key} fill={STATUS[r.key]} />
            ))}
            <LabelList dataKey="count" position="right" fill="#52514e" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
