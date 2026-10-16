import type { Metadata } from "next";

import { AppShell } from "@/components/layout/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: "StockWise AI",
  description: "AI-powered demand forecasting and explainable inventory recommendations.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
