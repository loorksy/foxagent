"use client";

import { StrategyCard } from "./StrategyCard";
import type { StrategyRule } from "@/lib/types";
import { useT } from "@/i18n";

export function StrategyLibrary({ items }: { items: StrategyRule[] }) {
  const t = useT();
  if (!items.length) {
    return <p className="text-sm text-muted-foreground">{t("lab.empty")}</p>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {items.map((rule) => (
        <StrategyCard key={rule.id} rule={rule} />
      ))}
    </div>
  );
}
