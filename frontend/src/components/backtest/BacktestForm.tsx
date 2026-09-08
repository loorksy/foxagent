"use client";

import { useEffect, useState } from "react";
import { useBacktest } from "@/stores/backtest";
import { useStrategyLab } from "@/stores/strategyLab";
import { useT, type MessageKey } from "@/i18n";

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
    if (!strategies.length) void loadLab();
  }, [loadLab, strategies.length]);

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
      className="grid gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-4"
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
      <label className="text-xs text-muted-foreground">
        {t("backtest.timeframe")}
        <select
          className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm"
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
        >
          <option value="M15">M15</option>
          <option value="H1">H1</option>
          <option value="H4">H4</option>
        </select>
      </label>
      <label className="text-xs text-muted-foreground">
        {t("backtest.strategy")}
        <select
          className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
        >
          <option value="">{t("backtest.allStrategies")}</option>
          {options.map((rule) => (
            <option key={rule.id} value={rule.id}>
              {rule.id.startsWith("gold_") ? t(`bot.strategy.${rule.id}` as MessageKey) : rule.name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-muted-foreground">
        {t("backtest.days")}
        <select
          className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          {[90, 180, 365, 730].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={running}
        className="self-end rounded-lg border border-border py-2 text-sm font-semibold disabled:opacity-50"
      >
        {running ? t("backtest.running") : t("backtest.run")}
      </button>
    </form>
  );
}
