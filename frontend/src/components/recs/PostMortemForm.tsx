"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export function PostMortemForm({ recId, defaultThesis = "" }: { recId: string; defaultThesis?: string }) {
  const t = useT();
  const [thesis, setThesis] = useState(defaultThesis);
  const [invalidation, setInvalidation] = useState("");
  const [outcome, setOutcome] = useState("");
  const [lesson, setLesson] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.postmortem(recId, { thesis, invalidation, outcome, lesson });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    }
  }

  return (
    <form data-testid="postmortem-form" className="mt-3 space-y-2 rounded-xl border border-border bg-card p-3 text-sm" onSubmit={(e) => void onSubmit(e)}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("recs.postmortem")}</p>
      <label className="block text-xs text-muted-foreground">
        {t("recs.thesis")}
        <textarea className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" rows={2} value={thesis} onChange={(e) => setThesis(e.target.value)} />
      </label>
      <label className="block text-xs text-muted-foreground">
        {t("recs.invalidation")}
        <textarea className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" rows={2} value={invalidation} onChange={(e) => setInvalidation(e.target.value)} />
      </label>
      <label className="block text-xs text-muted-foreground">
        {t("recs.outcome")}
        <input className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" value={outcome} onChange={(e) => setOutcome(e.target.value)} />
      </label>
      <label className="block text-xs text-muted-foreground">
        {t("recs.lesson")}
        <textarea className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" rows={2} value={lesson} onChange={(e) => setLesson(e.target.value)} />
      </label>
      <button type="submit" className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold">
        {t("recs.savePostmortem")}
      </button>
      {saved ? <p className="text-xs text-buy">{t("recs.postmortemSaved")}</p> : null}
      {error ? <p className="text-xs text-sell">{error}</p> : null}
    </form>
  );
}
