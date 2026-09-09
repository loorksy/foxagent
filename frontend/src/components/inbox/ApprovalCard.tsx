"use client";

import { useState } from "react";
import Link from "next/link";
import type { InboxItem } from "@/lib/types";
import { useT } from "@/i18n";

export function ApprovalCard({
  item,
  onApprove,
  onReject,
}: {
  item: InboxItem;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string, reason: string) => Promise<void>;
}) {
  const t = useT();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sig = item.payload?.signal;

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("inbox.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{item.title}</p>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground" dir="ltr">
            {item.summary}
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
          {item.severity}
        </span>
      </div>
      {sig ? (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">{t("inbox.entry")}</dt>
            <dd className="font-mono" dir="ltr">
              {sig.entryPrice}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("inbox.stop")}</dt>
            <dd className="font-mono" dir="ltr">
              {sig.stopLoss}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">R</dt>
            <dd className="font-mono" dir="ltr">
              {sig.riskReward}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("bot.confidence")}</dt>
            <dd className="font-mono" dir="ltr">
              {(sig.confidence * 100).toFixed(0)}%
            </dd>
          </div>
        </dl>
      ) : null}
      <label className="mt-3 block text-xs text-muted-foreground">
        {t("inbox.rejectReason")}
        <textarea
          className="mt-1 min-h-16 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t("inbox.rejectPlaceholder")}
        />
      </label>
      {error ? <p className="mt-2 text-xs text-sell">{error}</p> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(() => onApprove(item.id))}
          className="min-h-11 flex-1 rounded-lg bg-foreground px-3 py-2 text-sm font-semibold text-background disabled:opacity-50"
        >
          {t("inbox.approve")}
        </button>
        <button
          type="button"
          disabled={busy || !reason.trim()}
          onClick={() => void run(() => onReject(item.id, reason.trim()))}
          className="min-h-11 flex-1 rounded-lg border border-border px-3 py-2 text-sm font-semibold disabled:opacity-50"
        >
          {t("inbox.reject")}
        </button>
        <Link href={item.sourceHref} className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm text-muted-foreground hover:text-foreground">
          {t("inbox.openSource")}
        </Link>
      </div>
    </article>
  );
}
