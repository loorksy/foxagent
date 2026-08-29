"use client";

import { RecommendationCard } from "@/components/chat/RecommendationCard";
import { useRecommendations } from "@/stores/recommendations";

export function RecommendationsPage() {
  const items = useRecommendations((s) => s.items);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium tracking-tight">التوصيات</h1>
      <p className="mt-1 text-sm text-muted-foreground">سجل الإعدادات التي أنتجها الوكيل، مع البطاقة نفسها التي تظهر في الشات.</p>
      <div className="mt-6 space-y-3">
        {items.length === 0 ? (
          <p className="rounded-xl border border-border bg-card px-4 py-8 text-center text-sm text-muted-foreground">
            لا توجد توصيات بعد. اطلب تحليلاً من المحادثة.
          </p>
        ) : (
          items.map((rec) => <RecommendationCard key={rec.id} rec={rec} />)
        )}
      </div>
    </div>
  );
}
