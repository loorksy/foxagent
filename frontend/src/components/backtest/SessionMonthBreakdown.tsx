"use client";

import { useBacktest } from "@/stores/backtest";
import { useT, type MessageKey } from "@/i18n";
import { ar } from "@/i18n/messages/ar";
import { cn } from "@/lib/utils";
import type { BacktestBucket } from "@/lib/types";

function BucketRow({ label, bucket, ltrLabel }: { label: string; bucket: BacktestBucket; ltrLabel?: boolean }) {
  const wr = bucket.winRate || 0;
  const positive = (bucket.totalR || 0) >= 0;
  return (
    <li className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className={cn("font-medium", ltrLabel && "font-mono tabular-nums")} dir={ltrLabel ? "ltr" : undefined}>
          {label}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground" dir="ltr">
          {bucket.trades} · WR {(wr * 100).toFixed(0)}% ·{" "}
          <span className={cn("font-bold", positive ? "text-buy" : "text-sell")}>
            {positive ? "+" : ""}
            {(bucket.totalR || 0).toFixed(2)}R
          </span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted" dir="ltr">
        <div
          className={cn("h-full rounded-full", wr >= 0.5 ? "bg-buy" : "bg-sell")}
          style={{ width: `${Math.min(wr * 100, 100)}%` }}
        />
      </div>
    </li>
  );
}

export function SessionMonthBreakdown() {
  const report = useBacktest((s) => s.report);
  const t = useT();
  if (!report) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
        {t("backtest.noReport")}
      </p>
    );
  }
  const sessions = Object.entries(report.bySession || {});
  const months = Object.entries(report.byMonth || {});
  if (!sessions.length && !months.length) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
        {t("backtest.empty")}
      </p>
    );
  }
  const sessionLabel = (id: string) => {
    const key = `lab.session.${id}` as MessageKey;
    return key in ar ? t(key) : id;
  };

  return (
    <section className="grid gap-3 md:grid-cols-2">
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t("backtest.bySession")}
        </h2>
        <ul className="mt-3 space-y-3">
          {sessions.map(([key, bucket]) => (
            <BucketRow key={key} label={sessionLabel(key)} bucket={bucket} />
          ))}
        </ul>
      </div>
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t("backtest.byMonth")}
        </h2>
        <ul className="mt-3 space-y-3">
          {months.map(([key, bucket]) => (
            <BucketRow key={key} label={key} bucket={bucket} ltrLabel />
          ))}
        </ul>
      </div>
    </section>
  );
}
