"use client";

import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";

export function SessionMonthBreakdown() {
  const report = useBacktest((s) => s.report);
  const t = useT();
  const bySession = report?.bySession;
  const byMonth = report?.byMonth;
  if (!report || (!bySession && !byMonth)) return null;
  return (
    <section className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">{t("backtest.bySession")}</h2>
        <ul className="mt-2 space-y-1 text-xs">
          {Object.entries(bySession || {}).map(([key, bucket]) => (
            <li key={key} className="flex justify-between font-mono" dir="ltr">
              <span>{key}</span>
              <span>
                {bucket.trades} · WR {(bucket.winRate * 100).toFixed(0)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">{t("backtest.byMonth")}</h2>
        <ul className="mt-2 space-y-1 text-xs">
          {Object.entries(byMonth || {}).map(([key, bucket]) => (
            <li key={key} className="flex justify-between font-mono" dir="ltr">
              <span>{key}</span>
              <span>
                {bucket.trades} · {bucket.totalR}R
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
