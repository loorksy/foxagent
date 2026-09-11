"use client";

import { useMemo } from "react";
import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

function Sparkline({ points, positive }: { points: number[]; positive: boolean }) {
  if (points.length < 2) return null;
  const min = Math.min(0, ...points);
  const max = Math.max(0, ...points);
  const span = Math.max(max - min, 0.01);
  const w = 96;
  const h = 28;
  const d = points
    .map((y, i) => {
      const x = (i / (points.length - 1)) * (w - 2) + 1;
      const py = h - 2 - ((y - min) / span) * (h - 4);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${py.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className={cn("h-7 w-24", positive ? "text-buy" : "text-sell")}
      aria-hidden="true"
    >
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.8" />
    </svg>
  );
}

export function BacktestSummary() {
  const report = useBacktest((s) => s.report);
  const t = useT();
  const equity = useMemo(() => {
    let eq = 0;
    return (report?.trades ?? []).map((tr) => {
      eq += tr.pnlR;
      return eq;
    });
  }, [report]);
  if (!report) return null;

  const netPositive = report.totalR >= 0;
  const pfDisplay = Number.isFinite(report.profitFactor) ? report.profitFactor.toFixed(2) : "∞";
  const cards: {
    label: string;
    value: string;
    tone: string;
    sub?: React.ReactNode;
  }[] = [
    {
      label: t("backtest.netR"),
      value: `${netPositive ? "+" : ""}${report.totalR.toFixed(2)}R`,
      tone: netPositive ? "text-buy" : "text-sell",
      sub: <Sparkline points={equity} positive={netPositive} />,
    },
    {
      label: t("backtest.winRate"),
      value: `${(report.winRate * 100).toFixed(1)}%`,
      tone: report.winRate >= 0.5 ? "text-buy" : "text-sell",
      sub: (
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground" dir="ltr">
          {report.wins} {t("backtest.wins")} · {report.losses} {t("backtest.losses")}
        </span>
      ),
    },
    {
      label: t("backtest.pf"),
      value: pfDisplay,
      tone: report.profitFactor >= 1 ? "text-buy" : "text-sell",
      sub: (
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground" dir="ltr">
          {t("backtest.avgR")} {report.averageR.toFixed(2)}
        </span>
      ),
    },
    {
      label: t("backtest.dd"),
      value: `-${report.maxDrawdownR.toFixed(2)}R`,
      tone: report.maxDrawdownR > 0 ? "text-sell" : "text-muted-foreground",
    },
    {
      label: t("backtest.trades"),
      value: String(report.totalTrades),
      tone: "text-foreground",
      sub: (
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground" dir="ltr">
          {report.candlesTested.toLocaleString("en-US")} {t("backtest.candles")}
        </span>
      ),
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      {cards.map((card) => (
        <div key={card.label} className="rounded-xl border border-border bg-card p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{card.label}</p>
          <p className={cn("mt-1.5 font-mono text-2xl font-bold tabular-nums", card.tone)} dir="ltr">
            {card.value}
          </p>
          {card.sub ? <div className="mt-1.5">{card.sub}</div> : null}
        </div>
      ))}
    </section>
  );
}
