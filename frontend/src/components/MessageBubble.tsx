"use client";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";
import { useRecommendations } from "@/stores/recommendations";
import { useWorkspace } from "@/stores/workspace";
import { Bot, User, LineChart } from "lucide-react";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const recs = useRecommendations((s) => s.items);
  const applyToChart = useWorkspace((s) => s.applyToChart);
  const rec = recs.find((r) => r.id === message.recommendationId);

  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  return (
    <div className={cn("flex gap-2.5 enter", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/10",
          isUser ? "bg-gold-500/20 text-gold-400" : "bg-cyan-400/10 text-cyan-300"
        )}
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </div>
      <div
        className={cn(
          "max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
          isUser
            ? "bg-gold-500/15 text-slate-100"
            : isSystem
              ? "border border-white/10 bg-white/5 text-slate-400"
              : "glass text-slate-200"
        )}
      >
        <p className="whitespace-pre-wrap">
          {message.text || (message.streaming ? "Synthesizing…" : "")}
          {message.streaming && <span className="ml-1 inline-block h-3 w-1.5 animate-pulse bg-gold-400" />}
        </p>
        {rec && (
          <button
            type="button"
            onClick={() => {
              applyToChart(rec.klineOverlays, rec.focusTimestamp, rec.id);
            }}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-gold-500/30 bg-gold-500/10 px-2 py-1 text-[11px] font-medium text-gold-400 hover:bg-gold-500/20"
          >
            <LineChart className="h-3 w-3" />
            View on Chart
          </button>
        )}
      </div>
    </div>
  );
}
