"use client";

import { useBacktest } from "@/stores/backtest";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";

export function StrategyComparison() {
  const report = useBacktest((s) => s.report);
  const t = useT();
  const rows = Object.entries(report?.byStrategy ?? {});
  if (!report) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
        {t("backtest.noReport")}
      </p>
    );
  }
  if (!rows.length) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
        {t("backtest.empty")}
      </p>
    );
  }
  const sorted = [...rows].sort(([, a], [, b]) => (b.totalR || 0) - (a.totalR || 0));
  const strategyLabel = (id: string) => (id.startsWith("gold_") ? t(`bot.strategy.${id}` as MessageKey) : id);

  return (
    <section className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full min-w-[32rem] text-sm">
        <thead className="bg-muted/40 text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.strategy")}</th>
            <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.trades")}</th>
            <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.winRate")}</th>
            <th className="px-3 py-2.5 text-end font-semibold">ΣR</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(([id, stats]) => {
            const wr = stats.winRate || 0;
            const totalR = stats.totalR || 0;
            return (
              <tr key={id} className="border-t border-border/60 even:bg-muted/20">
                <td className="px-3 py-2 font-medium">{strategyLabel(id)}</td>
                <td className="px-3 py-2 font-mono tabular-nums" dir="ltr">
                  {stats.trades}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2" dir="ltr">
                    <span className="font-mono text-xs tabular-nums">{(wr * 100).toFixed(1)}%</span>
                    <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                      <span
                        className={cn("block h-full rounded-full", wr >= 0.5 ? "bg-buy" : "bg-sell")}
                        style={{ width: `${Math.min(wr * 100, 100)}%` }}
                      />
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2 text-end">
                  <span
                    className={cn("font-mono font-bold tabular-nums", totalR >= 0 ? "text-buy" : "text-sell")}
                    dir="ltr"
                  >
                    {totalR >= 0 ? "+" : ""}
                    {totalR.toFixed(2)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
