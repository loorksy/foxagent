"use client";

import { useEffect } from "react";
import { useSettings } from "@/stores/settings";
import { useT, type MessageKey } from "@/i18n";

const AGENTS = ["multi_strategy", "pattern_notes", "news_candle"] as const;
const STRATEGIES = [
  "gold_liquidity_sniper",
  "gold_breakout",
  "gold_trend_follow",
  "gold_reversal",
  "gold_scalp",
] as const;
const SESSIONS = ["london", "ny", "asian"] as const;

function toggle(list: string[] | undefined, id: string): string[] {
  const current = list || [];
  return current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
}

export function StrategySelector() {
  const form = useSettings((s) => s.form);
  const patchForm = useSettings((s) => s.patchForm);
  const load = useSettings((s) => s.load);
  const save = useSettings((s) => s.save);
  const t = useT();

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-4">
      <h2 className="text-sm font-semibold">{t("bot.strategies")}</h2>
      <div className="flex flex-wrap gap-2">
        {AGENTS.map((agent) => (
          <label key={agent} className="flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs">
            <input
              type="checkbox"
              checked={(form.botAgents || AGENTS).includes(agent)}
              onChange={() => patchForm({ botAgents: toggle(form.botAgents || [...AGENTS], agent) })}
            />
            {t(`bot.agent.${agent}` as MessageKey)}
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {STRATEGIES.map((id) => (
          <label key={id} className="flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs">
            <input
              type="checkbox"
              checked={(form.botActiveStrategies || STRATEGIES).includes(id)}
              onChange={() => patchForm({ botActiveStrategies: toggle(form.botActiveStrategies || [...STRATEGIES], id) })}
            />
            {t(`bot.strategy.${id}` as MessageKey)}
          </label>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-xs text-muted-foreground">
          {t("bot.maxRisk")}
          <input
            className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
            value={String(form.botMaxRiskPercent ?? 1)}
            onChange={(e) => patchForm({ botMaxRiskPercent: Number(e.target.value) || 1 })}
          />
        </label>
        <label className="text-xs text-muted-foreground">
          {t("bot.minRr")}
          <input
            className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
            value={String(form.botMinRr ?? 2)}
            onChange={(e) => patchForm({ botMinRr: Number(e.target.value) || 2 })}
          />
        </label>
        <div className="text-xs text-muted-foreground">
          {t("bot.sessions")}
          <div className="mt-1 flex flex-wrap gap-2">
            {SESSIONS.map((id) => (
              <label key={id} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={(form.botAllowedSessions || SESSIONS).includes(id)}
                  onChange={() => patchForm({ botAllowedSessions: toggle(form.botAllowedSessions || [...SESSIONS], id) })}
                />
                {id}
              </label>
            ))}
          </div>
        </div>
      </div>
      <button type="button" onClick={() => void save()} className="rounded-lg border border-border px-3 py-2 text-sm font-semibold">
        {t("settings.save")}
      </button>
    </section>
  );
}
