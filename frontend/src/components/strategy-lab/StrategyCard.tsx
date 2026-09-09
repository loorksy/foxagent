"use client";

import type { StrategyRule } from "@/lib/types";
import { useStrategyLab } from "@/stores/strategyLab";
import { cn } from "@/lib/utils";
import { useT, type MessageKey } from "@/i18n";

const STATUS_TONE: Record<string, string> = {
  draft: "border-warning/40 bg-warning/10 text-warning",
  validated: "border-info/40 bg-info/10 text-info",
  active: "border-buy/45 bg-buy/10 text-buy",
  rejected: "border-sell/40 bg-sell/10 text-sell",
  archived: "border-border bg-muted/40 text-muted-foreground",
  experimenting: "border-info/40 bg-info/10 text-info",
};

export function StrategyCard({ rule, compact = false }: { rule: StrategyRule; compact?: boolean }) {
  const t = useT();
  const validate = useStrategyLab((s) => s.validate);
  const approve = useStrategyLab((s) => s.approve);
  const reject = useStrategyLab((s) => s.reject);
  const remove = useStrategyLab((s) => s.remove);
  const pin = useStrategyLab((s) => s.pin);
  const unpin = useStrategyLab((s) => s.unpin);
  const locked = rule.source === "builtin";
  const statusKey = `lab.status.${rule.status}` as MessageKey;
  const sourceKey = `lab.source.${rule.source}` as MessageKey;

  return (
    <article className="rounded-xl border border-border bg-card p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{rule.name}</h3>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground" dir="ltr">
            {rule.id}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-semibold", STATUS_TONE[rule.status] || STATUS_TONE.draft)}>
            {t(statusKey)}
          </span>
          <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">{t(sourceKey)}</span>
        </div>
      </div>
      {!compact && rule.description ? <p className="mt-2 text-muted-foreground">{rule.description}</p> : null}
      <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
        {(rule.timeframes || []).map((tf) => (
          <span key={tf} className="rounded-full border border-border px-2 py-0.5 font-mono" dir="ltr">
            {tf}
          </span>
        ))}
        <span className="rounded-full border border-border px-2 py-0.5">{t(`lab.direction.${rule.direction}` as MessageKey)}</span>
        <span className="rounded-full border border-border px-2 py-0.5" dir="ltr">
          TP {rule.tp1_r}/{rule.tp2_r}R
        </span>
      </div>
      {rule.rejection_reason ? (
        <p className="mt-2 text-xs text-sell">
          {t("lab.rejectReason")}: {rule.rejection_reason}
        </p>
      ) : null}
      {locked || rule.status === "validated" || rule.status === "active" || rule.status === "archived" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {rule.pinned ? (
            <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-xs" onClick={() => void unpin(rule.id)}>
              {t("lab.unpin")}
            </button>
          ) : (
            <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold" onClick={() => void pin(rule.id)}>
              {t("lab.pin")}
            </button>
          )}
        </div>
      ) : null}
      {locked ? (
        <p className="mt-1 text-[11px] text-muted-foreground">{t("lab.builtinLocked")}</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {rule.status === "draft" || rule.status === "validated" ? (
            <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold" onClick={() => void validate(rule.id)}>
              {t("lab.validate")}
            </button>
          ) : null}
          {rule.status === "validated" ? (
            <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold" onClick={() => void approve(rule.id)}>
              {t("lab.approve")}
            </button>
          ) : null}
          {rule.status !== "rejected" && rule.status !== "archived" ? (
            <button
              type="button"
              className="rounded-lg border border-border px-3 py-1.5 text-xs"
              onClick={() => void reject(rule.id, t("lab.reject"))}
            >
              {t("lab.reject")}
            </button>
          ) : null}
          {rule.status === "draft" ? (
            <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-xs text-sell" onClick={() => void remove(rule.id)}>
              {t("lab.delete")}
            </button>
          ) : null}
        </div>
      )}
    </article>
  );
}
