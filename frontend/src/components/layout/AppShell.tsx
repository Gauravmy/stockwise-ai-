"use client";

import { BarChart3, Boxes, Database, LayoutDashboard, LineChart, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { cx } from "@/components/ui";
import { ToastProvider } from "@/components/ui/Toast";
import { API_BASE_URL } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview", Icon: LayoutDashboard },
  { href: "/forecasting", label: "Demand Forecasting", Icon: LineChart },
  { href: "/inventory", label: "Inventory", Icon: Boxes },
  { href: "/data", label: "Data Management", Icon: Database },
  { href: "/insights", label: "Insights & Reports", Icon: BarChart3 },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cx(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active ? "bg-navy-800 text-white" : "text-navy-200 hover:bg-navy-800/60 hover:text-white",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-3">
      <div className="flex h-7 w-7 items-center justify-center rounded bg-accent text-sm font-bold text-white">S</div>
      <div>
        <p className="text-sm font-semibold text-white">StockWise AI</p>
        <p className="text-[11px] text-navy-300">Demand &amp; inventory</p>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <ToastProvider>
      <div className="min-h-screen lg:flex">
        <aside className="hidden w-60 flex-none flex-col gap-6 bg-navy-950 py-5 lg:flex lg:sticky lg:top-0 lg:h-screen">
          <Brand />
          <div className="px-2">
            <NavLinks />
          </div>
          <p className="mt-auto break-all px-4 text-[11px] text-navy-400">API: {API_BASE_URL}</p>
        </aside>

        <header className="sticky top-0 z-30 flex items-center justify-between bg-navy-950 px-4 py-3 lg:hidden">
          <Brand />
          <button
            className="rounded p-1.5 text-navy-100 hover:bg-navy-800"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close navigation" : "Open navigation"}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </header>
        {open && (
          <div className="sticky top-[52px] z-20 bg-navy-950 px-2 pb-3 lg:hidden">
            <NavLinks onNavigate={() => setOpen(false)} />
          </div>
        )}

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </ToastProvider>
  );
}
