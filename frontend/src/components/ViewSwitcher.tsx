"use client";

import { cn } from "@/lib/utils";
import type { ViewMode } from "@/lib/types";
import { Columns2, MessageSquareText, CandlestickChart } from "lucide-react";

const OPTIONS: { id: ViewMode; label: string; icon: typeof Columns2 }[] = [
  { id: "split", label: "Split View", icon: Columns2 },
  { id: "chart", label: "Full Chart", icon: CandlestickChart },
  { id: "chat", label: "Full Chat", icon: MessageSquareText },
];

export function ViewSwitcher({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
}) {
  return (
    <div className="flex items-center gap-0.5 rounded-lg border border-white/10 bg-black/30 p-0.5">
      {OPTIONS.map((opt) => {
        const Icon = opt.icon;
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium tracking-wide transition",
              active ? "bg-gold-500/20 text-gold-400 shadow-glow" : "text-slate-400 hover:text-slate-200"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
