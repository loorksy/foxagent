"use client";

import { useBot } from "@/stores/bot";
import { useT } from "@/i18n";

export function BotStatusCard() {
  const status = useBot((s) => s.status);
  const start = useBot((s) => s.start);
  const stop = useBot((s) => s.stop);
  const signals = useBot((s) => s.signals);
  const t = useT();
  const running = Boolean(status?.running);

  return (
    <section className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-[11px] uppercase text-muted-foreground">{running ? t("bot.running") : t("bot.stopped")}</p>
        <p className="mt-2 font-mono text-sm" dir="ltr">
          {Math.floor(status?.uptimeSeconds || 0)}s
        </p>
        <button
          type="button"
          onClick={() => void (running ? stop() : start())}
          className="mt-3 w-full rounded-lg border border-border py-2 text-sm font-semibold"
        >
          {running ? t("bot.stop") : t("bot.start")}
        </button>
      </div>
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-[11px] uppercase text-muted-foreground">{t("bot.signals")}</p>
        <p className="mt-2 text-2xl font-semibold">{status?.signalsToday ?? signals.length}</p>
      </div>
      <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
        XAU_USD · ICT / SMC
      </div>
    </section>
  );
}
