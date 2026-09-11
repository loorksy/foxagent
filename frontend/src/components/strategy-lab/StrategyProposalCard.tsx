"use client";

import type { StrategyRule, StrategyValidation } from "@/lib/types";
import { useStrategyLab } from "@/stores/strategyLab";
import { ValidationResult } from "./ValidationResult";
import { useT, type MessageKey } from "@/i18n";
import { useState } from "react";

export function StrategyProposalCard({
  rule,
  validation,
}: {
  rule: StrategyRule;
  validation?: StrategyValidation;
}) {
  const t = useT();
  const validate = useStrategyLab((s) => s.validate);
  const approve = useStrategyLab((s) => s.approve);
  const reject = useStrategyLab((s) => s.reject);
  const last = useStrategyLab((s) => s.lastValidation);
  const [busy, setBusy] = useState(false);
  const shown = validation || (last?.strategy?.id === rule.id ? last : null);

  return (
    <div data-testid="strategy-proposal-card" className="mt-2 space-y-3 rounded-xl border border-border bg-card p-3 text-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("lab.chatProposal")}</p>
      <div>
        <p className="flex flex-wrap items-center gap-2 font-semibold">
          {rule.name}
          {rule.kind === "python" ? (
            <span className="rounded-full border border-info/40 bg-info/10 px-2 py-0.5 text-[11px] font-semibold text-info">{t("lab.codeBadge")}</span>
          ) : null}
        </p>
        <p className="mt-1 text-muted-foreground">{rule.description}</p>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground" dir="ltr">
          {rule.id} · {(rule.timeframes || []).join(" ")} · {t(`lab.status.${rule.status}` as MessageKey)}
        </p>
      </div>
      {rule.status === "draft" || rule.status === "validated" ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
            onClick={async () => {
              setBusy(true);
              await validate(rule.id);
              setBusy(false);
            }}
          >
            {t("lab.validate")}
          </button>
          {rule.status === "validated" ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
              onClick={() => void approve(rule.id)}
            >
              {t("lab.pin")}
            </button>
          ) : null}
          <button
            type="button"
            disabled={busy}
            className="rounded-lg border border-border px-3 py-1.5 text-xs disabled:opacity-50"
            onClick={() => void reject(rule.id, t("lab.reject"))}
          >
            {t("lab.reject")}
          </button>
        </div>
      ) : null}
      {shown ? <ValidationResult result={shown} /> : null}
    </div>
  );
}
