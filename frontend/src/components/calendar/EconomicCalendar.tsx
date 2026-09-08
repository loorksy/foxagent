"use client";

import { useEffect, useMemo, useState } from "react";
import type { EconomicEvent } from "@/lib/types";
import { useCalendar } from "@/stores/calendar";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

const IMPACT_TONE: Record<string, string> = {
  critical: "bg-sell/20 text-sell border-sell/40",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/40",
  medium: "bg-warning/15 text-warning border-warning/40",
  low: "bg-muted text-muted-foreground border-border",
};

function goldMark(bias?: string) {
  if (bias === "positive") return "↑";
  if (bias === "negative") return "↓";
  return "=";
}

function Countdown({ iso }: { iso: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return <span dir="ltr">—</span>;
  const delta = target - now;
  if (delta <= 0) return <span dir="ltr">00:00:00</span>;
  const h = Math.floor(delta / 3_600_000);
  const m = Math.floor((delta % 3_600_000) / 60_000);
  const s = Math.floor((delta % 60_000) / 1000);
  return (
    <span dir="ltr">
      {String(h).padStart(2, "0")}:{String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}
    </span>
  );
}

export function EconomicCalendar({ compact = false }: { compact?: boolean }) {
  const events = useCalendar((s) => s.events);
  const source = useCalendar((s) => s.source);
  const load = useCalendar((s) => s.load);
  const t = useT();

  useEffect(() => {
    void load(48);
  }, [load]);

  const next = useMemo(() => {
    const now = Date.now();
    return events.find((e) => new Date(e.timestamp).getTime() > now) || events[0];
  }, [events]);

  return (
    <div className={cn("space-y-4", compact && "space-y-3")}>
      {next && (
        <div className="rounded-xl border border-border bg-card px-4 py-3 text-sm">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{t("calendar.countdown")}</p>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">{next.title}</span>
            <Countdown iso={next.timestamp} />
          </div>
        </div>
      )}
      {!events.length ? (
        <p className="text-sm text-muted-foreground">{t("calendar.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[36rem] text-start text-sm">
            <thead className="bg-muted/40 text-[11px] uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">USD</th>
                <th className="px-3 py-2 font-medium">{t("calendar.impact")}</th>
                <th className="px-3 py-2 font-medium">{t("calendar.gold")}</th>
                <th className="px-3 py-2 font-medium">F / P / A</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev: EconomicEvent) => (
                <tr key={ev.id} className="border-t border-border/70">
                  <td className="px-3 py-2">
                    <p className="font-medium">{ev.title}</p>
                    <p className="text-[11px] text-muted-foreground" dir="ltr">
                      {new Date(ev.timestamp).toISOString().replace("T", " ").slice(0, 16)}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn("rounded-full border px-2 py-0.5 text-[11px]", IMPACT_TONE[ev.impact] || IMPACT_TONE.medium)}>
                      {ev.impact}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-lg">{goldMark(ev.gold_impact)}</td>
                  <td className="px-3 py-2 font-mono text-[12px]" dir="ltr">
                    {ev.forecast ?? "—"} / {ev.previous ?? "—"} / {ev.actual ?? "—"} {ev.unit || ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {source ? <p className="text-[11px] text-muted-foreground">{source}</p> : null}
    </div>
  );
}
