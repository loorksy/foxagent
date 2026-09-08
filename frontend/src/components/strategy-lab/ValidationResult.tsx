"use client";

import type { StrategyValidation } from "@/lib/types";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function ValidationResult({ result }: { result: StrategyValidation | null }) {
  const t = useT();
  if (!result) return null;
  const report = result.report;
  return (
    <section className="rounded-xl border border-border bg-card p-4 text-sm">
      <p className={cn("font-semibold", result.passed ? "text-buy" : "text-sell")}>
        {result.passed ? t("lab.passed") : t("lab.failed")}
      </p>
      {result.strategy ? (
        <p className="mt-1 text-muted-foreground">
          {result.strategy.name} <span className="font-mono text-[11px]" dir="ltr">{result.strategy.id}</span>
        </p>
      ) : null}
      {report ? (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
          <Stat label={t("backtest.trades")} value={String(report.totalTrades)} />
          <Stat label="WR" value={`${(report.winRate * 100).toFixed(1)}%`} />
          <Stat label={t("backtest.pf")} value={report.profitFactor.toFixed(2)} />
          <Stat label={t("backtest.totalR")} value={report.totalR.toFixed(2)} />
          <Stat label={t("backtest.dd")} value={`${report.maxDrawdownR.toFixed(2)}R`} />
        </dl>
      ) : null}
      {result.reasons?.length ? (
        <ul className="mt-3 list-disc space-y-1 ps-5 text-xs text-sell">
          {result.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {result.detail && !result.ok ? <p className="mt-2 text-xs text-sell">{result.detail}</p> : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono font-semibold" dir="ltr">
        {value}
      </dd>
    </div>
  );
}
