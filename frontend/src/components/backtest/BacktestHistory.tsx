"use client";

import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export function BacktestHistory() {
  const history = useBacktest((s) => s.history);
  const loadReport = useBacktest((s) => s.loadReport);
  const t = useT();
  if (!history.length) {
    return <p className="text-sm text-muted-foreground">{t("backtest.historyEmpty")}</p>;
  }
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">{t("backtest.history")}</h2>
      <ul className="space-y-2">
        {history.filter((row) => row.id).map((row) => (
          <li key={row.id}>
            <button
              type="button"
              onClick={() => void loadReport(row.id as string)}
              className="w-full rounded-xl border border-border bg-card px-3 py-2 text-start text-sm"
            >
              <span className="font-mono text-xs" dir="ltr">
                {row.strategyId || "all"} · {row.timeframe}
              </span>
              <span className="ms-2 text-muted-foreground">WR {(row.winRate * 100).toFixed(0)}%</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
