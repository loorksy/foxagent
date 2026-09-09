"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function NewsBotPage() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [windows, setWindows] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    void api.botsNews().then((row) => {
      setOpen(row.open);
      setWindows(row.windows || []);
    }).catch(() => undefined);
  }, []);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium">{t("bots.news")}</h1>
      <p className="text-sm text-muted-foreground">{t("bots.newsHelp")}</p>
      {open ? (
        <ul className="space-y-2">
          {windows.map((w) => (
            <li key={String(w.eventId)} className="rounded-xl border border-border bg-card p-4 text-sm">
              <p className="font-semibold">{String(w.title)}</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground" dir="ltr">
                {String(w.minutes)}m · {String(w.strategy || "window")}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("bots.newsEmpty")}</p>
      )}
    </div>
  );
}
