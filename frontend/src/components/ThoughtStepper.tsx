"use client";

import { useChat } from "@/stores/chat";
import { cn } from "@/lib/utils";
import { Check, Loader2, Circle } from "lucide-react";

export function ThoughtStepper() {
  const phases = useChat((s) => s.phases);
  const thoughts = useChat((s) => s.thoughts);
  const streaming = useChat((s) => s.streaming);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Agent Mind Stream</p>
        {streaming && <span className="text-[10px] text-cyan-300">live</span>}
      </div>
      <ol className="space-y-2">
        {phases.map((p) => (
          <li key={p.id} className="flex gap-2.5">
            <div className="mt-0.5">
              {p.status === "complete" ? (
                <Check className="h-3.5 w-3.5 text-emerald-400" />
              ) : p.status === "active" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-gold-400" />
              ) : (
                <Circle className="h-3.5 w-3.5 text-slate-600" />
              )}
            </div>
            <div>
              <p
                className={cn(
                  "text-xs font-medium",
                  p.status === "active" ? "text-gold-400" : p.status === "complete" ? "text-slate-200" : "text-slate-500"
                )}
              >
                Phase {p.id}: {p.name}
              </p>
              <p className="text-[11px] text-slate-500">{p.detail}</p>
            </div>
          </li>
        ))}
      </ol>
      {thoughts.length > 0 && (
        <div className="max-h-28 overflow-y-auto rounded-md border border-white/5 bg-black/30 p-2 font-mono text-[10px] leading-relaxed text-cyan-200/80">
          {thoughts.slice(-8).map((t, i) => (
            <p key={i} className="enter">
              ▸ {t}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
