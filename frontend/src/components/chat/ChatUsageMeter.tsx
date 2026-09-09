"use client";

import { useT } from "@/i18n";
import type { TokenUsage } from "@/lib/types";

function compact(n: number | undefined): string {
  const value = Number(n || 0);
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 10_000) return `${Math.round(value / 1000)}k`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(Math.round(value));
}

export function formatUsage(usage: TokenUsage): string {
  const parts = [`${compact(usage.inputTokens)}↓`, `${compact(usage.outputTokens)}↑`];
  const cache = (usage.cacheReadTokens || 0) + (usage.cacheCreationTokens || 0);
  if (cache) parts.push(`${compact(cache)} cache`);
  if (usage.estimatedUsd && usage.estimatedUsd >= 0.0001) {
    parts.push(`~$${usage.estimatedUsd < 0.01 ? usage.estimatedUsd.toFixed(3) : usage.estimatedUsd.toFixed(2)}`);
  }
  return parts.join(" · ");
}

export function ChatUsageMeter({
  usage,
  label,
  live,
}: {
  usage: TokenUsage | null | undefined;
  label?: string;
  live?: boolean;
}) {
  const t = useT();
  if (!usage || !usage.totalTokens) return null;
  return (
    <p className="mt-1 font-mono text-[11px] leading-4 text-muted-foreground/80" dir="ltr" title={t("chat.usage.hint")}>
      {live ? `${t("chat.usage.live")} · ` : null}
      {label ? `${label} · ` : null}
      {formatUsage(usage)}
      {usage.calls ? ` · ${usage.calls}×` : null}
    </p>
  );
}
