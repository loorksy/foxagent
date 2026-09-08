"use client";

import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export function BacktestSummary() {
  const report = useBacktest((s) => s.report);
  const t = useT();
  if (!report) return null;
  const cells = [
    [t("backtest.trades"), String(report.totalTrades)],
    [t("bot.winRate"), `${(report.winRate * 100).toFixed(1)}%`],
    [t("backtest.totalR"), report.totalR.toFixed(2)],
    [t("backtest.pf"), report.profitFactor.toFixed(2)],
    [t("backtest.dd"), `-${report.maxDrawdownR.toFixed(2)}R`],
  ];
  return (
    <section className="grid gap-3 sm:grid-cols-5">
      {cells.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-border bg-card p-4">
          <p className="text-[11px] uppercase text-muted-foreground">{label}</p>
          <p className="mt-2 font-mono text-lg">{value}</p>
        </div>
      ))}
    </section>
  );
}
