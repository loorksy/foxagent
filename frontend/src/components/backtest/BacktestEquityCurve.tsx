"use client";

import { useMemo } from "react";
import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export function BacktestEquityCurve() {
  const trades = useBacktest((s) => s.report?.trades || []);
  const t = useT();
  const points = useMemo(() => {
    let eq = 0;
    return trades.map((tr) => {
      eq += tr.pnlR;
      return eq;
    });
  }, [trades]);
  if (points.length < 2) return null;
  const min = Math.min(0, ...points);
  const max = Math.max(0, ...points);
  const span = Math.max(max - min, 0.01);
  const w = 640;
  const h = 160;
  const d = points
    .map((y, i) => {
      const x = (i / (points.length - 1)) * (w - 16) + 8;
      const py = h - 8 - ((y - min) / span) * (h - 16);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${py.toFixed(1)}`;
    })
    .join(" ");
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <p className="mb-2 text-[11px] uppercase text-muted-foreground">{t("backtest.curve")}</p>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-40 w-full" role="img" aria-label={t("backtest.curve")}>
        <path d={d} fill="none" stroke="currentColor" strokeWidth="2" className="text-foreground" />
      </svg>
    </section>
  );
}
