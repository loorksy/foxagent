"use client";

import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export function BacktestTradesTable() {
  const trades = useBacktest((s) => s.report?.trades || []);
  const t = useT();
  if (!trades.length) return <p className="text-sm text-muted-foreground">{t("backtest.empty")}</p>;
  return (
    <section className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[44rem] text-sm">
        <thead className="bg-muted/40 text-[11px] uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-start">{t("backtest.strategy")}</th>
            <th className="px-3 py-2 text-start">{t("backtest.entry")}</th>
            <th className="px-3 py-2 text-start">{t("backtest.exit")}</th>
            <th className="px-3 py-2 text-start">{t("backtest.reason")}</th>
            <th className="px-3 py-2 text-start">R</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, 80).map((tr, i) => (
            <tr key={`${tr.entryTime}-${i}`} className="border-t border-border/70">
              <td className="px-3 py-2">
                {tr.strategyId} · {tr.direction}
              </td>
              <td className="px-3 py-2 font-mono text-[11px]" dir="ltr">
                {tr.entryTime?.replace("T", " ").slice(0, 16)} · {tr.entryPrice}
              </td>
              <td className="px-3 py-2 font-mono text-[11px]" dir="ltr">
                {tr.exitTime?.replace("T", " ").slice(0, 16)} · {tr.exitPrice}
              </td>
              <td className="px-3 py-2">{tr.exitReason}</td>
              <td className="px-3 py-2 font-mono">{tr.pnlR.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
