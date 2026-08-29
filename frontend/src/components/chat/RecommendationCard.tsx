"use client";

import { useState } from "react";
import { CandlestickChart, Check, Copy, Shield, Target, TrendingDown, TrendingUp } from "lucide-react";
import type { TradeRecommendation } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/stores/workspace";
import { useSessions } from "@/stores/sessions";
import { formatPrice } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { displaySymbol } from "@/lib/constants";
import { recStatusKey, useT } from "@/i18n";

function CopyPrice({ value }: { value: number }) {
  const [copied, setCopied] = useState(false);
  const t = useT();
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(String(value)).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      className="relative inline-flex size-4 items-center justify-center text-muted-foreground after:absolute after:-inset-3 hover:text-foreground"
      aria-label={t("rec.copy")}
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

const STATUS_TONE: Record<string, string> = {
  PENDING: "border-warning/40 bg-warning/10 text-warning",
  ACTIVE: "border-info/40 bg-info/10 text-info",
  IN_PROFIT: "border-buy/45 bg-buy/10 text-buy",
  HIT_TP1: "border-buy/45 bg-buy/10 text-buy",
  HIT_TP2: "border-success/45 bg-success/10 text-success",
  STOPPED_OUT: "border-sell/40 bg-sell/10 text-sell",
  CANCELLED: "border-border bg-muted/40 text-muted-foreground",
  EXPIRED: "border-border bg-muted/40 text-muted-foreground",
};

export function RecommendationCard({ rec }: { rec: TradeRecommendation }) {
  const applyToChart = useWorkspace((s) => s.applyToChart);
  const router = useRouter();
  const activeId = useSessions((s) => s.activeId);
  const t = useT();
  const buy = rec.tradeSetup.action === "BUY";
  const DirIcon = buy ? TrendingUp : TrendingDown;
  const pillTone = STATUS_TONE[rec.status] || STATUS_TONE.PENDING;
  const { entryPrice, stopLoss, takeProfitLevels, riskRewardRatio } = rec.tradeSetup;

  return (
    <div data-testid="recommendation-card" className="mt-2 overflow-hidden rounded-xl border border-border bg-card text-sm">
      <div className="flex flex-col">
        <div className={cn("flex flex-col gap-2.5 border-b border-border/60 p-3", buy ? "bg-buy/10" : "bg-sell/10")}>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground">
              ICT
            </span>
            <span className="rounded-full border border-border bg-card px-2 py-0.5 font-mono text-[11px] text-muted-foreground" dir="ltr">
              {rec.timeframe}
            </span>
            <button
              type="button"
              onClick={() => {
                applyToChart(rec.klineOverlays || [], rec.focusTimestamp, rec.id);
                if (activeId) router.push(`/agents/${activeId}?app=chart`);
              }}
              className="ms-auto inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-[11px] text-foreground hover:bg-muted"
            >
              <CandlestickChart className="h-3 w-3" />
              {t("rec.showOnChart")}
            </button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className={cn("text-[11px] font-semibold uppercase tracking-wider", buy ? "text-buy" : "text-sell")}>
                {buy ? t("rec.buy") : t("rec.sell")}
              </p>
              <p className={cn("mt-0.5 flex items-center gap-2 font-mono text-xl font-extrabold", buy ? "text-buy" : "text-sell")} dir="ltr">
                {displaySymbol(rec.symbol)}
                <DirIcon className="h-5 w-5" />
              </p>
            </div>
            <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold", pillTone)}>
              {t(recStatusKey(rec.status))}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-3 gap-y-3 p-3 sm:grid-cols-3">
          <Level label={t("rec.entry")} value={entryPrice} tone="text-foreground" />
          <Level label={t("rec.stopLoss")} value={stopLoss} tone="text-sell" icon="sl" />
          {takeProfitLevels.slice(0, 3).map((tp) => (
            <Level key={tp.level} label={t("rec.target", { n: tp.level })} value={tp.price} tone="text-buy" icon="tp" />
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border/60 px-3 py-2.5 text-[11px] text-muted-foreground">
          <span className="min-w-0 flex-1">{rec.rationale.slice(0, 140)}</span>
          <span className="shrink-0 font-mono font-bold tabular-nums text-foreground" dir="ltr">
            R:R {riskRewardRatio.toFixed(2)}
          </span>
          {rec.pnlPips != null ? (
            <span className={cn("font-mono font-bold", rec.pnlPips >= 0 ? "text-buy" : "text-sell")} dir="ltr">
              {rec.pnlPips >= 0 ? "+" : ""}
              {rec.pnlPips.toFixed(2)}R
            </span>
          ) : null}
        </div>
        {rec.confluence.length > 0 && (
          <div className="flex flex-wrap gap-1.5 border-t border-border/40 bg-muted/50 px-3 py-2.5">
            {rec.confluence.slice(0, 6).map((c) => (
              <span key={c} className="rounded-full bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                {c}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Level({ label, value, tone, icon }: { label: string; value: number; tone: string; icon?: "sl" | "tp" }) {
  return (
    <div className="min-w-0">
      <p className="flex items-center gap-1 text-[10px] text-muted-foreground">
        {icon === "sl" ? <Shield className="h-3 w-3" /> : icon === "tp" ? <Target className="h-3 w-3" /> : null}
        {label}
      </p>
      <p className="mt-0.5 flex items-center gap-1.5">
        <span className={cn("font-mono text-sm font-bold tabular-nums", tone)} dir="ltr">
          {formatPrice(value, value > 50 ? 2 : 5)}
        </span>
        <CopyPrice value={value} />
      </p>
    </div>
  );
}
