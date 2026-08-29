"use client";

import { RecommendationCard } from "@/components/chat/RecommendationCard";
import { useRecommendations } from "@/stores/recommendations";
import { useT } from "@/i18n";

export function RecommendationsPage() {
  const items = useRecommendations((s) => s.items);
  const t = useT();

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium tracking-tight">{t("recs.title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("recs.subtitle")}</p>
      <div className="mt-6 space-y-3">
        {items.length === 0 ? (
          <p className="rounded-xl border border-border bg-card px-4 py-8 text-center text-sm text-muted-foreground">
            {t("recs.empty")}
          </p>
        ) : (
          items.map((rec) => <RecommendationCard key={rec.id} rec={rec} />)
        )}
      </div>
    </div>
  );
}
