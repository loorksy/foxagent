"use client";

import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export function StrategyComparison() {
  const byStrategy = useBacktest((s) => s.report?.byStrategy || {});
  const t = useT();
  const rows = Object.entries(byStrategy);
  if (!rows.length) return null;
  return (
    <section className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[32rem] text-sm">
        <thead className="bg-muted/40 text-[11px] uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-start">{t("backtest.strategy")}</th>
            <th className="px-3 py-2 text-start">{t("backtest.trades")}</th>
            <th className="px-3 py-2 text-start">{t("bot.winRate")}</th>
            <th className="px-3 py-2 text-start">ΣR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([id, stats]) => (
            <tr key={id} className="border-t border-border/70">
              <td className="px-3 py-2">{id}</td>
              <td className="px-3 py-2">{stats.trades}</td>
              <td className="px-3 py-2">{((stats.winRate || 0) * 100).toFixed(1)}%</td>
              <td className="px-3 py-2 font-mono">{(stats.totalR || 0).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
