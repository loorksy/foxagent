"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BotDesk } from "@/components/bot/BotDesk";
import { CircuitBadge } from "@/components/bot/CircuitBadge";
import { DeskStatusCard } from "@/components/desk/DeskStatusCard";
import { api } from "@/lib/api";
import { useInbox } from "@/stores/inbox";
import { useT } from "@/i18n";

export default function BotsRoom() {
  const t = useT();
  const desk = useInbox((s) => s.desk);
  const [agents, setAgents] = useState<string[]>([]);
  const [newsOpen, setNewsOpen] = useState(false);
  const [safeMode, setSafeMode] = useState(false);

  useEffect(() => {
    void api.botsRoom().then((row) => {
      setAgents(Array.isArray(row.agents) ? (row.agents as string[]) : []);
      const news = row.news as { open?: boolean } | undefined;
      setNewsOpen(Boolean(news?.open));
      const circuits = row.circuits as { safeMode?: boolean } | undefined;
      setSafeMode(Boolean(circuits?.safeMode));
    }).catch(() => undefined);
  }, []);

  return (
    <div className="fox-scroll mx-auto w-full max-w-5xl flex-1 space-y-6 overflow-y-auto px-4 py-6">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight">{t("bots.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("bots.subtitle")}</p>
      </div>
      <DeskStatusCard desk={desk} />
      <CircuitBadge halted={safeMode} />
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { href: "/bots/structure", label: t("bots.structure"), on: agents.includes("multi_strategy") },
          { href: "/bots/patterns", label: t("bots.patterns"), on: agents.includes("pattern_notes") },
          { href: "/bots/news", label: t("bots.news"), on: agents.includes("news_candle") || newsOpen },
        ].map((card) => (
          <Link key={card.href} href={card.href} className="rounded-xl border border-border bg-card p-4">
            <p className="font-semibold">{card.label}</p>
            <p className="mt-1 text-xs text-muted-foreground">{card.on ? t("bots.enabled") : t("bots.disabled")}</p>
          </Link>
        ))}
      </div>
      <BotDesk />
    </div>
  );
}
