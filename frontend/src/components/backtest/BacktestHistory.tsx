"use client";

import { useBacktest } from "@/stores/backtest";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";

export function BacktestHistory() {
  const history = useBacktest((s) => s.history);
  const report = useBacktest((s) => s.report);
  const loadReport = useBacktest((s) => s.loadReport);
  const t = useT();
  if (!history.length) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
        {t("backtest.historyEmpty")}
      </p>
    );
  }
  const strategyLabel = (id?: string | null) =>
    id ? (id.startsWith("gold_") ? t(`bot.strategy.${id}` as MessageKey) : id) : t("backtest.allStrategies");

  return (
    <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {history
        .filter((row) => row.id)
        .map((row) => {
          const current = Boolean(report?.id && row.id === report.id);
          const positive = (row.totalR || 0) >= 0;
          return (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => void loadReport(row.id as string)}
                className={cn(
                  "w-full rounded-xl border bg-card p-3 text-start transition-colors hover:border-foreground/40",
                  current ? "border-foreground/60" : "border-border"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold">{strategyLabel(row.strategyId)}</span>
                  <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] uppercase text-muted-foreground" dir="ltr">
                    {row.timeframe}
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[11px] tabular-nums text-muted-foreground" dir="ltr">
                  <span>
                    {row.totalTrades} · WR {((row.winRate || 0) * 100).toFixed(0)}%
                  </span>
                  <span className={cn("font-bold", positive ? "text-buy" : "text-sell")}>
                    {positive ? "+" : ""}
                    {(row.totalR || 0).toFixed(2)}R
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                  <span className="font-mono" dir="ltr">
                    {row.createdAt ? row.createdAt.replace("T", " ").slice(0, 16) : ""}
                  </span>
                  {current ? <span className="font-semibold text-foreground">{t("backtest.current")}</span> : null}
                </div>
              </button>
            </li>
          );
        })}
    </ul>
  );
}
