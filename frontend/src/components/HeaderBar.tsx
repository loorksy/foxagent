"use client";

import { Activity, Settings } from "lucide-react";
import { ViewSwitcher } from "./ViewSwitcher";
import { PERIODS, displaySymbol } from "@/lib/constants";
import { cn, formatPrice } from "@/lib/utils";
import { useWorkspace } from "@/stores/workspace";
import { useSettings } from "@/stores/settings";

export function HeaderBar() {
  const symbol = useWorkspace((s) => s.symbol);
  const period = useWorkspace((s) => s.period);
  const setPeriod = useWorkspace((s) => s.setPeriod);
  const prices = useWorkspace((s) => s.prices);
  const viewMode = useWorkspace((s) => s.viewMode);
  const setViewMode = useWorkspace((s) => s.setViewMode);
  const dataMode = useWorkspace((s) => s.dataMode);
  const setOpen = useSettings((s) => s.setOpen);
  const px = prices[symbol];
  const digits = symbol.startsWith("XAU") ? 2 : symbol.includes("JPY") ? 3 : 5;

  return (
    <header className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-2.5">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gold-500/20 text-gold-400">
          <Activity className="h-5 w-5" />
        </div>
        <div>
          <p className="font-display text-lg leading-none text-gold-400">FoxAgent</p>
          <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Autonomous ICT Desk</p>
        </div>
        <div className="ml-2 hidden items-center gap-2 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 md:flex">
          <span className="live-dot h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <span className="font-mono text-sm text-slate-100">{displaySymbol(symbol)}</span>
          <span className="font-mono text-sm text-gold-400">{px ? formatPrice(px.mid, digits) : "—"}</span>
          {px && <span className="text-[10px] text-slate-500">spr {formatPrice(px.spread, digits)}</span>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-white/10 bg-black/30 p-0.5">
          {PERIODS.map((p) => (
            <button
              key={p.text}
              type="button"
              onClick={() => setPeriod(p)}
              className={cn(
                "rounded-md px-2 py-1 font-mono text-[11px]",
                period.text === p.text ? "bg-white/10 text-gold-400" : "text-slate-500 hover:text-slate-200"
              )}
            >
              {p.text}
            </button>
          ))}
        </div>
        <ViewSwitcher value={viewMode} onChange={setViewMode} />
        <span
          className={cn(
            "rounded-full px-2 py-1 text-[10px] uppercase tracking-wider",
            dataMode === "oanda" ? "bg-emerald-400/10 text-emerald-300" : "bg-white/5 text-slate-400"
          )}
        >
          {dataMode === "oanda" ? "OANDA live" : "Simulator"}
        </span>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:border-gold-500/40 hover:text-gold-400"
        >
          <Settings className="h-3.5 w-3.5" />
          Settings
        </button>
      </div>
    </header>
  );
}
