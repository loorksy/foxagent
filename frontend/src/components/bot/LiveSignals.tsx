"use client";

import { useBot } from "@/stores/bot";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

export function LiveSignals() {
  const signals = useBot((s) => s.signals);
  const promote = useBot((s) => s.promote);
  const t = useT();

  if (!signals.length) {
    return <p className="text-sm text-muted-foreground">{t("bot.emptySignals")}</p>;
  }

  return (
    <section className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[40rem] text-sm">
        <thead className="bg-muted/40 text-[11px] uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-start">Signal</th>
            <th className="px-3 py-2 text-start">{t("bot.confidence")}</th>
            <th className="px-3 py-2 text-start">R:R</th>
            <th className="px-3 py-2 text-start">Status</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {signals.map((sig) => (
            <tr key={sig.id} className="border-t border-border/70">
              <td className="px-3 py-2">
                <p className="font-medium">
                  {sig.strategyId} · {sig.signalType}
                </p>
                <p className="font-mono text-[11px] text-muted-foreground" dir="ltr">
                  {sig.entryPrice} / {sig.stopLoss}
                </p>
              </td>
              <td className="px-3 py-2">{(sig.confidence * 100).toFixed(0)}%</td>
              <td className="px-3 py-2">{sig.riskReward}</td>
              <td className="px-3 py-2">{sig.status}</td>
              <td className="px-3 py-2 text-end">
                {sig.confidence > 0.8 && (
                  <button
                    type="button"
                    onClick={() => void promote(sig.id)}
                    className={cn("rounded-full border border-border px-2 py-1 text-[11px]")}
                  >
                    {t("bot.promote")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
