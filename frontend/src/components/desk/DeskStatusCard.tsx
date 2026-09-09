"use client";

import Link from "next/link";
import type { DeskStatus } from "@/lib/types";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function DeskStatusCard({ desk, compact }: { desk: DeskStatus | null; compact?: boolean }) {
  const t = useT();
  if (!desk) return null;
  const chips = [
    { ok: !desk.paused, label: desk.paused ? t("desk.paused") : t("desk.live") },
    { ok: desk.botRunning, label: desk.botRunning ? t("desk.botOn") : t("desk.botOff") },
    { ok: !desk.warehouseStale, label: desk.warehouseStale ? t("desk.warehouseStale") : t("desk.warehouseFresh") },
  ];
  return (
    <section className={cn("rounded-xl border border-border bg-card p-3", compact && "p-2.5")}>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((chip) => (
          <span
            key={chip.label}
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium",
              chip.ok ? "bg-muted text-muted-foreground" : "bg-warning/15 text-warning"
            )}
          >
            {chip.label}
          </span>
        ))}
        {desk.openCount > 0 ? (
          <Link href="/inbox" className="rounded-full bg-foreground px-2 py-0.5 text-[11px] font-medium text-background">
            {t("desk.inboxCount", { n: desk.openCount })}
          </Link>
        ) : (
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{t("desk.inboxEmpty")}</span>
        )}
      </div>
      {desk.nextEventTitle ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {t("desk.nextEvent", { title: desk.nextEventTitle, m: desk.nextEventMinutes ?? "—" })}
        </p>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">{t("desk.noEvent")}</p>
      )}
    </section>
  );
}
