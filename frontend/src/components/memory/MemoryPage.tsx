"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace";
import type { MemoryEntry } from "@/lib/types";
import { useT } from "@/i18n";

export function MemoryPage() {
  const symbol = useWorkspace((s) => s.symbol);
  const t = useT();
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [context, setContext] = useState("");

  useEffect(() => {
    void api
      .memory()
      .then((data) => setEntries(data.entries || []))
      .catch(() => setEntries([]));
  }, []);

  useEffect(() => {
    void api
      .memoryContext(symbol)
      .then((data) => setContext(data.context || ""))
      .catch(() => setContext(""));
  }, [symbol]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium tracking-tight">{t("memory.title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("memory.subtitle")}</p>

      <section className="mt-6 rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">{t("memory.context", { symbol })}</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
          {context.trim() ? context : t("memory.noContext")}
        </p>
      </section>

      <div className="mt-6 space-y-3">
        {entries.length === 0 ? (
          <p className="rounded-xl border border-border bg-card px-4 py-8 text-center text-sm text-muted-foreground">
            {t("memory.empty")}
          </p>
        ) : (
          entries.map((entry) => (
            <article key={entry.id} className="rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
                <span>{entry.symbol}</span>
                <span>{entry.kind}</span>
                <span>{entry.status}</span>
                {entry.rating ? <span>{entry.rating}</span> : null}
              </div>
              <p className="mt-1.5 font-mono text-sm">{entry.decision}</p>
              {entry.reflection ? <p className="mt-1 text-sm text-muted-foreground">{entry.reflection}</p> : null}
              {entry.recommendationId ? (
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">ref={entry.recommendationId}</p>
              ) : null}
            </article>
          ))
        )}
      </div>
    </div>
  );
}
