"use client";

import { useRecommendations } from "@/stores/recommendations";
import { useWorkspace } from "@/stores/workspace";
import { displaySymbol } from "@/lib/constants";
import { cn, formatPrice } from "@/lib/utils";
import { LineChart } from "lucide-react";
import type { TradeRecommendation } from "@/lib/types";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING: "bg-amber-400/15 text-amber-300",
    ACTIVE: "bg-cyan-400/15 text-cyan-300",
    IN_PROFIT: "bg-emerald-400/15 text-emerald-300",
    HIT_TP1: "bg-emerald-400/15 text-emerald-300",
    HIT_TP2: "bg-emerald-500/20 text-emerald-200",
    STOPPED_OUT: "bg-rose-400/15 text-rose-300",
  };
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", map[status] || "bg-white/10 text-slate-300")}>
      {status.replace("_", " ")}
    </span>
  );
}

function Card({ rec }: { rec: TradeRecommendation }) {
  const applyToChart = useWorkspace((s) => s.applyToChart);
  const setSymbol = useWorkspace((s) => s.setSymbol);
  const setTimeframe = useWorkspace((s) => s.setTimeframe);
  const buy = rec.tradeSetup.action === "BUY";
  const digits = rec.symbol.includes("USD") && rec.symbol.startsWith("XAU") ? 2 : rec.symbol.includes("JPY") ? 3 : 5;

  return (
    <article className="enter rounded-xl border border-white/8 bg-white/[0.03] p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-100">
            {displaySymbol(rec.symbol)} <span className="text-slate-500">•</span>{" "}
            <span className={buy ? "text-emerald-400" : "text-rose-400"}>
              {rec.tradeSetup.action} {rec.tradeSetup.orderType}
            </span>
          </p>
          <p className="text-[11px] text-slate-500">
            {rec.timeframe} · {new Date(rec.timestamp).toLocaleString()}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="rounded-md bg-gold-500/15 px-2 py-0.5 font-mono text-[11px] text-gold-400">
            R:R 1:{rec.tradeSetup.riskRewardRatio.toFixed(1)}
          </span>
          <StatusBadge status={rec.status} />
          {rec.pnlPips != null && (
            <span className={cn("font-mono text-[10px]", rec.pnlPips >= 0 ? "text-emerald-400" : "text-rose-400")}>
              {rec.pnlPips >= 0 ? "+" : ""}
              {rec.pnlPips.toFixed(1)}R
            </span>
          )}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-4 gap-2 font-mono text-[11px]">
        <div>
          <p className="text-slate-500">Entry</p>
          <p>{formatPrice(rec.tradeSetup.entryPrice, digits)}</p>
        </div>
        <div>
          <p className="text-slate-500">SL</p>
          <p className="text-rose-300">{formatPrice(rec.tradeSetup.stopLoss, digits)}</p>
        </div>
        {rec.tradeSetup.takeProfitLevels.slice(0, 2).map((tp) => (
          <div key={tp.level}>
            <p className="text-slate-500">TP{tp.level}</p>
            <p className="text-emerald-300">{formatPrice(tp.price, digits)}</p>
          </div>
        ))}
      </div>
      {rec.confluence?.length > 0 && (
        <ul className="mt-2 space-y-1 text-[11px] text-slate-400">
          {rec.confluence.slice(0, 3).map((c) => (
            <li key={c}>▹ {c}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 line-clamp-3 text-[12px] leading-relaxed text-slate-300">{rec.rationale}</p>
      <button
        type="button"
        onClick={() => {
          setSymbol(rec.symbol);
          setTimeframe(rec.timeframe);
          applyToChart(rec.klineOverlays, rec.focusTimestamp, rec.id);
        }}
        className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-gold-500/30 bg-gold-500/10 px-2.5 py-1.5 text-[11px] font-medium text-gold-400 hover:bg-gold-500/20"
      >
        <LineChart className="h-3.5 w-3.5" />
        Apply to Chart
      </button>
    </article>
  );
}

export function RecommendationsLedger() {
  const items = useRecommendations((s) => s.items);

  return (
    <section className="glass flex h-full min-h-0 flex-col overflow-hidden rounded-2xl">
      <header className="border-b border-white/5 px-3 py-2.5">
        <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">قسم التوصيات</p>
        <h2 className="text-sm font-semibold text-slate-100">Live Recommendations & Signals</h2>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {items.length === 0 ? (
          <p className="px-2 py-8 text-center text-xs text-slate-500">No setups yet. Run Generate Setup from the omnibar.</p>
        ) : (
          items.map((rec) => <Card key={rec.id} rec={rec} />)
        )}
      </div>
    </section>
  );
}
