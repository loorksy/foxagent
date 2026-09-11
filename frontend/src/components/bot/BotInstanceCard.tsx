"use client";

import { useState } from "react";
import { Bell, FlaskConical, LineChart, Play, Square, Trash2, Zap } from "lucide-react";
import type { BotInstance, BotInstanceType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useT, type MessageKey } from "@/i18n";

const TYPE_META: Record<
  BotInstanceType,
  { icon: typeof LineChart; color: string; bg: string; border: string }
> = {
  strategy: { icon: LineChart, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30" },
  quant: { icon: FlaskConical, color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/30" },
  alerts: { icon: Bell, color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30" },
  execution: { icon: Zap, color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/30" },
};

function formatSignalTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

type Props = {
  bot: BotInstance;
  onToggleEnabled: (enabled: boolean) => void;
  onStart: () => void;
  onStop: () => void;
  onDelete: () => void;
  busy?: boolean;
};

export function BotInstanceCard({ bot, onToggleEnabled, onStart, onStop, onDelete, busy }: Props) {
  const t = useT();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const meta = TYPE_META[bot.type];
  const Icon = meta.icon;
  const running = Boolean(bot.running);

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                meta.bg,
                meta.border,
                meta.color
              )}
            >
              <Icon className="size-3.5" aria-hidden />
              {t(`bots.type.${bot.type}` as MessageKey)}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[11px] font-medium",
                running ? "bg-buy/15 text-buy" : "bg-muted text-muted-foreground"
              )}
            >
              {running ? t("bots.running") : t("bots.stopped")}
            </span>
          </div>
          <h3 className="mt-2 truncate font-semibold">{bot.name}</h3>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            className="size-4 accent-foreground"
            checked={bot.enabled}
            disabled={busy}
            onChange={(e) => onToggleEnabled(e.target.checked)}
          />
        </label>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <dt className="text-muted-foreground">{t("bots.cycles")}</dt>
          <dd className="font-mono" dir="ltr">{bot.stats.cycles}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("bots.interval")}</dt>
          <dd className="font-mono" dir="ltr">
            {bot.scanIntervalSeconds}
            {t("bots.seconds")}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted-foreground">{t("bots.lastSignal")}</dt>
          <dd className="font-mono" dir="ltr">
            {bot.stats.lastSignalAt ? formatSignalTime(bot.stats.lastSignalAt) : t("bots.noSignal")}
          </dd>
        </div>
        {bot.type === "execution" ? (
          <>
            <div>
              <dt className="text-muted-foreground">{t("bots.orderVolume")}</dt>
              <dd className="font-mono" dir="ltr">{bot.orderVolume}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t("bots.autoExecute")}</dt>
              <dd className={cn("font-medium", bot.autoExecute ? "text-sell" : "text-muted-foreground")}>
                {bot.autoExecute ? "ON" : "OFF"}
              </dd>
            </div>
          </>
        ) : null}
      </dl>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => (running ? onStop() : onStart())}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold",
            running ? "border-border" : "border-buy/40 bg-buy/10 text-buy"
          )}
        >
          {running ? <Square className="size-3.5" aria-hidden /> : <Play className="size-3.5" aria-hidden />}
          {running ? t("bots.stop") : t("bots.start")}
        </button>
        {confirmDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-sell">{t("bots.deleteConfirm")}</span>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                onDelete();
                setConfirmDelete(false);
              }}
              className="rounded-lg border border-sell/40 bg-sell/10 px-2 py-1 text-xs font-semibold text-sell"
            >
              {t("bots.delete")}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              className="rounded-lg border border-border px-2 py-1 text-xs"
            >
              {t("bots.wizard.cancel")}
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => setConfirmDelete(true)}
            className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs text-muted-foreground hover:text-sell"
          >
            <Trash2 className="size-3.5" aria-hidden />
            {t("bots.delete")}
          </button>
        )}
      </div>
    </article>
  );
}
