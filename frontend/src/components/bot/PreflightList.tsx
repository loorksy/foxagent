"use client";

import type { PreflightReport } from "@/lib/types";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function PreflightList({ report }: { report: PreflightReport | null }) {
  const t = useT();
  if (!report) return null;
  return (
    <ul className="space-y-1.5 rounded-xl border border-border bg-card p-3" aria-label={t("preflight.title")}>
      {report.checks.map((check) => (
        <li key={check.id} className="flex items-start gap-2 text-sm">
          <span
            className={cn(
              "mt-0.5 inline-block size-2.5 shrink-0 rounded-full",
              check.ok ? "bg-emerald-500" : check.blocking ? "bg-red-500" : "bg-amber-500"
            )}
          />
          <div className="min-w-0">
            <p className="font-medium">{check.label}</p>
            <p className="text-xs text-muted-foreground">{check.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
