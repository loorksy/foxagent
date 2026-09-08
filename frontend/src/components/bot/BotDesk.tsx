"use client";

import { useEffect } from "react";
import { useBot } from "@/stores/bot";
import { EconomicCalendar } from "@/components/calendar/EconomicCalendar";
import { BotStatusCard } from "./BotStatusCard";
import { AgentPerformance } from "./AgentPerformance";
import { LiveSignals } from "./LiveSignals";
import { StrategySelector } from "./StrategySelector";
import { useT } from "@/i18n";

export function BotDesk() {
  const load = useBot((s) => s.load);
  const t = useT();

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-5xl flex-1 space-y-6 overflow-y-auto px-4 py-6">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight">{t("bot.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("bot.subtitle")}</p>
      </div>
      <BotStatusCard />
      <AgentPerformance />
      <StrategySelector />
      <LiveSignals />
      <section>
        <h2 className="mb-3 text-sm font-semibold">{t("calendar.title")}</h2>
        <EconomicCalendar compact />
      </section>
    </div>
  );
}
