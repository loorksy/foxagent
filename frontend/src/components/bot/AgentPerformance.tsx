"use client";

import { useBot } from "@/stores/bot";
import { useT, type MessageKey } from "@/i18n";

const AGENTS = ["multi_strategy", "pattern_notes", "news_candle"];

export function AgentPerformance() {
  const performance = useBot((s) => s.performance);
  const t = useT();

  return (
    <section className="grid gap-3 md:grid-cols-3">
      {AGENTS.map((agent) => {
        const rows = performance.filter((p) => p.agentType === agent);
        const wins = rows.reduce((n, r) => n + (r.wins || 0), 0);
        const losses = rows.reduce((n, r) => n + (r.losses || 0), 0);
        const total = rows.reduce((n, r) => n + (r.totalSignals || 0), 0);
        const pnl = rows.reduce((n, r) => n + (r.averageWin || 0) * (r.wins || 0) + (r.averageLoss || 0) * (r.losses || 0), 0);
        return (
          <div key={agent} className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm font-semibold">{t(`bot.agent.${agent}` as MessageKey)}</p>
            <p className="mt-2 text-xs text-muted-foreground">
              {total} · {t("bot.winRate")} {(wins / (total || 1) * 100).toFixed(0)}%
            </p>
            <p className="mt-1 font-mono text-xs text-muted-foreground" dir="ltr">
              {wins}/{losses} · {pnl.toFixed(1)}
            </p>
          </div>
        );
      })}
    </section>
  );
}
