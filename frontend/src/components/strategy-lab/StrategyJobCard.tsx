"use client";

import Link from "next/link";
import type { StrategyExperimentJob } from "@/lib/types";
import { useStrategyLab } from "@/stores/strategyLab";
import { useT } from "@/i18n";

export function StrategyJobCard({ job }: { job: StrategyExperimentJob }) {
  const t = useT();
  const approve = useStrategyLab((s) => s.approve);
  const reject = useStrategyLab((s) => s.reject);
  const attempts = job.attempts;
  const latest = job.best || attempts[attempts.length - 1];
  const report = latest?.report;
  const sessions = latest?.strategy?.sessions || [];

  return (
    <div data-testid="strategy-job-card" className="mt-2 space-y-3 rounded-xl border border-border bg-card p-3 text-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("lab.chatJob")}</p>
      <div>
        <p className="font-semibold">{latest?.strategy?.name || job.strategyId}</p>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground" dir="ltr">
          {job.strategyId} · {attempts.length}/{job.maxAttempts || 8} · {job.status}
        </p>
        {sessions.length ? (
          <p className="mt-1 text-xs text-muted-foreground">{sessions.join(" · ")}</p>
        ) : null}
      </div>
      {report ? (
        <p className="font-mono text-[11px] text-muted-foreground" dir="ltr">
          WR {((report.winRate || 0) * 100).toFixed(0)}% · PF {report.profitFactor ?? "—"} · DD {report.maxDrawdownR ?? "—"}R
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {job.status === "awaiting_pin" ? t("lab.awaitingPin") : job.status === "exhausted" ? t("lab.exhausted") : t("lab.jobStatus") + ": " + job.status}
      </p>
      {job.passed && job.strategyId ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold"
            onClick={() => void approve(job.strategyId)}
          >
            {t("lab.pin")}
          </button>
          <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-xs" onClick={() => void reject(job.strategyId, t("lab.reject"))}>
            {t("lab.reject")}
          </button>
        </div>
      ) : null}
      <Link href={`/strategy-lab/jobs/${job.id}`} className="inline-block text-xs text-muted-foreground underline">
        {t("lab.jobTitle")}
      </Link>
    </div>
  );
}
