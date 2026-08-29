"use client";

import { Check, ChevronDown, Loader2 } from "lucide-react";
import { useState } from "react";
import { useChat } from "@/stores/chat";
import { cn } from "@/lib/utils";
import { phaseNameKey, useT } from "@/i18n";

export function ChatThinking() {
  const phases = useChat((s) => s.phases);
  const thoughts = useChat((s) => s.thoughts);
  const [open, setOpen] = useState(false);
  const active = phases.find((p) => p.status === "active");
  const t = useT();

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-9 items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        <span>{active ? t(phaseNameKey(active.id)) : t("chat.thinking")}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="mt-2 space-y-1.5 rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
          {phases.map((p) => (
            <li key={p.id} className="flex items-start gap-2 text-[12px]">
              {p.status === "complete" ? (
                <Check className="mt-0.5 h-3.5 w-3.5 text-buy" />
              ) : p.status === "active" ? (
                <Loader2 className="mt-0.5 h-3.5 w-3.5 animate-spin text-warning" />
              ) : (
                <span className="mt-1.5 size-1.5 rounded-full bg-muted-foreground/40" />
              )}
              <span className={p.status === "pending" ? "text-muted-foreground" : "text-foreground"}>{t(phaseNameKey(p.id))}</span>
            </li>
          ))}
          {thoughts.slice(-4).map((t, i) => (
            <li key={i} className="ps-6 font-mono text-[11px] text-muted-foreground">
              {t}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
