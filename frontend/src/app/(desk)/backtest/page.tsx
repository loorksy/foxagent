"use client";

import { useEffect, useState } from "react";
import { BacktestForm } from "@/components/backtest/BacktestForm";
import { BacktestSummary } from "@/components/backtest/BacktestSummary";
import { BacktestTradesTable } from "@/components/backtest/BacktestTradesTable";
import { BacktestEquityCurve } from "@/components/backtest/BacktestEquityCurve";
import { StrategyComparison } from "@/components/backtest/StrategyComparison";
import { BacktestHistory } from "@/components/backtest/BacktestHistory";
import { SessionMonthBreakdown } from "@/components/backtest/SessionMonthBreakdown";
import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

type TabId = "trades" | "breakdown" | "comparison" | "history" | "report";

export default function BacktestRoute() {
  const loadHistory = useBacktest((s) => s.loadHistory);
  const error = useBacktest((s) => s.error);
  const report = useBacktest((s) => s.report);
  const running = useBacktest((s) => s.running);
  const history = useBacktest((s) => s.history);
  const t = useT();
  const [tab, setTab] = useState<TabId>("trades");

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "trades", label: t("backtest.trades"), count: report?.trades.length },
    { id: "breakdown", label: t("backtest.breakdown") },
    { id: "comparison", label: t("backtest.comparison") },
    { id: "history", label: t("backtest.history"), count: history.length },
    { id: "report", label: t("backtest.textReport") },
  ];

  return (
    <div className="fox-scroll mx-auto w-full max-w-6xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight">{t("backtest.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("backtest.subtitle")}</p>
      </div>

      <BacktestForm />

      {error ? (
        <p className="rounded-xl border border-sell/40 bg-sell/10 px-4 py-3 text-sm text-sell">{error}</p>
      ) : null}

      {running ? (
        <div className="animate-pulse rounded-xl border border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
          {t("backtest.running")}
        </div>
      ) : report ? (
        <>
          <BacktestSummary />
          <BacktestEquityCurve />
        </>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-10 text-center text-sm text-muted-foreground">
          {t("backtest.noReport")}
        </div>
      )}

      <div role="tablist" className="flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm transition-colors",
              tab === item.id
                ? "border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            {item.label}
            {typeof item.count === "number" && item.count > 0 ? (
              <span className="ms-1.5 font-mono text-[10px] tabular-nums opacity-70" dir="ltr">
                {item.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {tab === "trades" ? <BacktestTradesTable /> : null}
      {tab === "breakdown" ? <SessionMonthBreakdown /> : null}
      {tab === "comparison" ? <StrategyComparison /> : null}
      {tab === "history" ? <BacktestHistory /> : null}
      {tab === "report" ? (
        report?.textReport ? (
          <pre
            className="overflow-x-auto rounded-xl border border-border bg-card p-4 text-[11px] leading-relaxed"
            dir="ltr"
          >
            {report.textReport}
          </pre>
        ) : (
          <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
            {report ? t("backtest.noTextReport") : t("backtest.noReport")}
          </p>
        )
      ) : null}
    </div>
  );
}
