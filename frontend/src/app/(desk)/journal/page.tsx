"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function JournalPage() {
  const t = useT();
  const [entries, setEntries] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    void api.journal().then((d) => setEntries(d.entries || [])).catch(() => setEntries([]));
  }, []);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium">{t("journal.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("journal.subtitle")}</p>
      {entries.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("journal.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {entries.map((row) => (
            <li key={String(row.id)} className="rounded-xl border border-border bg-card p-4 text-sm">
              <p className="font-semibold">{String(row.kind)}</p>
              <p className="mt-1 text-muted-foreground">{String(row.thesis || row.outcome || "")}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
