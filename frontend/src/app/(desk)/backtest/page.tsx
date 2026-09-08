"use client";

import { useEffect } from "react";
import { BacktestForm } from "@/components/backtest/BacktestForm";
import { BacktestSummary } from "@/components/backtest/BacktestSummary";
import { BacktestTradesTable } from "@/components/backtest/BacktestTradesTable";
import { BacktestEquityCurve } from "@/components/backtest/BacktestEquityCurve";
import { StrategyComparison } from "@/components/backtest/StrategyComparison";
import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export default function BacktestRoute() {
  const loadHistory = useBacktest((s) => s.loadHistory);
  const error = useBacktest((s) => s.error);
  const text = useBacktest((s) => s.report?.textReport);
  const t = useT();

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-5xl flex-1 space-y-6 overflow-y-auto px-4 py-6">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight">{t("backtest.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("backtest.subtitle")}</p>
      </div>
      <BacktestForm />
      {error ? <p className="text-sm text-sell">{error}</p> : null}
      <BacktestSummary />
      <BacktestEquityCurve />
      <StrategyComparison />
      <BacktestTradesTable />
      {text ? (
        <pre className="overflow-x-auto rounded-xl border border-border bg-card p-4 text-[11px] leading-relaxed" dir="ltr">
          {text}
        </pre>
      ) : null}
    </div>
  );
}
