"use client";

import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function CircuitBadge({ halted, reason }: { halted?: boolean; reason?: string }) {
  const t = useT();
  return (
    <span
      data-testid="circuit-badge"
      className={cn(
        "rounded-full border px-2 py-0.5 text-[11px] font-semibold",
        halted ? "border-sell/40 bg-sell/10 text-sell" : "border-border text-muted-foreground"
      )}
      title={reason}
    >
      {halted ? t("circuit.halted") : t("circuit.ok")}
    </span>
  );
}
