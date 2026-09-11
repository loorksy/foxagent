"use client";

import { useEffect, useState } from "react";
import { useBacktest } from "@/stores/backtest";
import { useStrategyLab } from "@/stores/strategyLab";
import { useT, type MessageKey } from "@/i18n";

const FIELD_CLASS =
  "mt-1 w-full rounded-lg border border-border bg-input px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export function BacktestForm() {
  const run = useBacktest((s) => s.run);
  const running = useBacktest((s) => s.running);
  const strategies = useStrategyLab((s) => s.items);
  const loadLab = useStrategyLab((s) => s.load);
  const t = useT();
  const [timeframe, setTimeframe] = useState("M15");
  const [strategyId, setStrategyId] = useState("");
  const [days, setDays] = useState(365);

  useEffect(() => {
    if (!useStrategyLab.getState().items.length) void loadLab();
  }, [loadLab]);

  const active = strategies.filter((r) => r.status === "active");
  const options = active.length
    ? active
    : [
        "gold_liquidity_sniper",
        "gold_breakout",
        "gold_trend_follow",
        "gold_reversal",
        "gold_scalp",
      ].map((id) => ({ id, name: id, status: "active" as const }));

  return (
    <form
      className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-card p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void run({
          timeframe,
          strategyId: strategyId || null,
          days,
          minRr: strategyId === "gold_scalp" ? 1 : 2,
        });
      }}
    >
      <label className="min-w-[6.5rem] flex-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground sm:flex-none">
        {t("backtest.timeframe")}
        <select className={FIELD_CLASS} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
          <option value="M15">M15</option>
          <option value="H1">H1</option>
          <option value="H4">H4</option>
        </select>
      </label>
      <label className="min-w-[11rem] flex-[2] text-[11px] font-semibold uppercase tracking-wide text-muted-foreground sm:flex-none">
        {t("backtest.strategy")}
        <select className={FIELD_CLASS} value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
          <option value="">{t("backtest.allStrategies")}</option>
          {options.map((rule) => (
            <option key={rule.id} value={rule.id}>
              {rule.id.startsWith("gold_") ? t(`bot.strategy.${rule.id}` as MessageKey) : rule.name}
            </option>
          ))}
        </select>
      </label>
      <label className="min-w-[6.5rem] flex-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground sm:flex-none">
        {t("backtest.days")}
        <select className={FIELD_CLASS} value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[90, 180, 365, 730].map((n) => (
            <option key={n} value={n}>
              {t("backtest.daysUnit", { n })}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={running}
        className="ms-auto h-[34px] rounded-lg bg-foreground px-5 text-sm font-semibold text-background transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {running ? t("backtest.running") : t("backtest.run")}
      </button>
    </form>
  );
}
