"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function BriefingPage() {
  const t = useT();
  const [body, setBody] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.briefing().then(setBody).catch(() => setBody({}));
  }, []);

  const events = (body?.events24h as Array<Record<string, unknown>>) || [];

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium">{t("briefing.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("briefing.subtitle")}</p>
      {!body ? (
        <p className="text-sm text-muted-foreground">{t("briefing.empty")}</p>
      ) : (
        <section className="space-y-2 rounded-xl border border-border bg-card p-4 text-sm">
          <p>
            {t("briefing.price")}: <span dir="ltr">{String(body.price ?? "—")}</span>
          </p>
          <p>
            Pause: {String(body.paused)} · {t("nav.bot")}: {String(body.botRunning)}
          </p>
          <p>
            {t("briefing.pending")}: {String(body.pendingApprovals)} · {t("briefing.unlabeled")}: {String(body.unlabeled)}
          </p>
          <div>
            <p className="mb-1 font-semibold">{t("briefing.events")}</p>
            {events.length === 0 ? (
              <p className="text-muted-foreground">{t("briefing.noEvents")}</p>
            ) : (
              <ul className="list-disc ps-5">
                {events.slice(0, 8).map((ev) => (
                  <li key={String(ev.id)}>{String(ev.title)}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
