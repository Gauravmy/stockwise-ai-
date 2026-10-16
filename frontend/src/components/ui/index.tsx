"use client";

import { AlertCircle, AlertTriangle, CheckCircle2, CircleAlert, Info, Loader2, OctagonAlert } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { ApiError } from "@/lib/api";
import { RISK_DESCRIPTIONS, RISK_LABELS } from "@/lib/format";
import type { Risk } from "@/lib/types";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-navy-900 sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-secondary">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("min-w-0 rounded-lg border border-navy-100 bg-surface shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-navy-100 px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-navy-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatCard({ label, value, hint, tone = "default" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "default" | "critical" | "warning" }) {
  return (
    <div className="rounded-lg border border-navy-100 bg-surface px-4 py-3 shadow-card">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</p>
      <p
        className={cx(
          "mt-1 text-2xl font-semibold",
          tone === "critical" ? "text-status-critical" : tone === "warning" ? "text-[#b45309]" : "text-navy-900",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "primary",
  loading,
  children,
  className,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean }) {
  const styles: Record<ButtonVariant, string> = {
    primary: "bg-navy-800 text-white hover:bg-navy-900 disabled:bg-navy-300",
    secondary: "border border-navy-200 bg-white text-navy-800 hover:bg-navy-50 disabled:text-navy-300",
    ghost: "text-navy-700 hover:bg-navy-50",
  };
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 disabled:cursor-not-allowed",
        styles[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-sm text-ink-muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded bg-navy-100", className)} aria-hidden />;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-navy-200 px-6 py-10 text-center">
      <p className="text-sm font-medium text-navy-800">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
      <AlertCircle className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">{error.message}</p>
        {error.requestId && <p className="mt-0.5 text-xs text-red-800/80">Request ID: {error.requestId}</p>}
      </div>
      {onRetry && (
        <Button variant="secondary" className="py-1" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

const ALERT_STYLES = {
  info: { cls: "border-blue-200 bg-blue-50 text-blue-900", Icon: Info },
  warning: { cls: "border-amber-200 bg-amber-50 text-amber-900", Icon: AlertTriangle },
  error: { cls: "border-red-200 bg-red-50 text-red-900", Icon: AlertCircle },
  success: { cls: "border-green-200 bg-green-50 text-green-900", Icon: CheckCircle2 },
};

export function Alert({ tone = "info", title, children }: { tone?: keyof typeof ALERT_STYLES; title?: string; children?: ReactNode }) {
  const { cls, Icon } = ALERT_STYLES[tone];
  return (
    <div className={cx("flex gap-2.5 rounded-md border px-3 py-2.5 text-sm", cls)} role={tone === "error" ? "alert" : undefined}>
      <Icon className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cx(title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}

export function WarningList({ items, tone = "warning", title }: { items: string[]; tone?: "warning" | "info"; title?: string }) {
  if (!items.length) return null;
  return (
    <Alert tone={tone} title={title}>
      <ul className="list-disc space-y-0.5 pl-4">
        {items.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </Alert>
  );
}

const RISK_STYLE: Record<Risk, { cls: string; Icon: typeof OctagonAlert }> = {
  critical: { cls: "bg-red-50 text-red-800 ring-red-200", Icon: OctagonAlert },
  high: { cls: "bg-orange-50 text-orange-800 ring-orange-200", Icon: AlertTriangle },
  moderate: { cls: "bg-amber-50 text-amber-800 ring-amber-200", Icon: CircleAlert },
  low: { cls: "bg-green-50 text-green-800 ring-green-200", Icon: CheckCircle2 },
};

export function RiskBadge({ risk }: { risk: Risk }) {
  const { cls, Icon } = RISK_STYLE[risk];
  return (
    <span
      className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", cls)}
      title={RISK_DESCRIPTIONS[risk]}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {RISK_LABELS[risk]}
    </span>
  );
}

export function Badge({ children, tone = "neutral", title }: { children: ReactNode; tone?: "neutral" | "blue" | "amber" | "green"; title?: string }) {
  const tones = {
    neutral: "bg-navy-50 text-navy-700 ring-navy-200",
    blue: "bg-blue-50 text-blue-800 ring-blue-200",
    amber: "bg-amber-50 text-amber-800 ring-amber-200",
    green: "bg-green-50 text-green-800 ring-green-200",
  };
  return (
    <span title={title} className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", tones[tone])}>
      {children}
    </span>
  );
}

export function Field({ label, htmlFor, hint, error, children }: { label: string; htmlFor: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-navy-800">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {error ? (
        <p className="mt-1 text-xs text-red-700" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>
      )}
    </div>
  );
}

export const inputClass =
  "block w-full rounded-md border border-navy-200 bg-white px-2.5 py-1.5 text-sm text-ink shadow-sm placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:bg-navy-50";

export function Th({ children, className, ...rest }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={cx("whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted", className)} {...rest}>
      {children}
    </th>
  );
}

export function Td({ children, className, ...rest }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cx("px-3 py-2 align-top text-sm", className)} {...rest}>
      {children}
    </td>
  );
}

export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="relative -mx-4 overflow-x-auto">
      <table className="min-w-full divide-y divide-navy-100">{children}</table>
    </div>
  );
}
