"use client";

import { create } from "zustand";
import type { TradeRecommendation } from "@/lib/types";
import { api } from "@/lib/api";

type RecState = {
  items: TradeRecommendation[];
  activeId: string | null;
  setActive: (id: string | null) => void;
  upsert: (rec: TradeRecommendation) => void;
  hydrate: () => Promise<void>;
  markFromPrice: (instrument: string, mid: number) => void;
};

export const useRecommendations = create<RecState>((set) => ({
  items: [],
  activeId: null,
  setActive: (activeId) => set({ activeId }),
  upsert: (rec) =>
    set((s) => {
      const idx = s.items.findIndex((i) => i.id === rec.id);
      const items = idx >= 0 ? s.items.map((i) => (i.id === rec.id ? rec : i)) : [rec, ...s.items];
      return { items, activeId: rec.id };
    }),
  hydrate: async () => {
    try {
      const data = await api.recommendations();
      set({ items: data.recommendations || [] });
    } catch {
      /* backend may still be booting */
    }
  },
  markFromPrice: (instrument, mid) =>
    set((s) => ({
      items: s.items.map((rec) => {
        if (rec.symbol !== instrument) return rec;
        if (["HIT_TP2", "STOPPED_OUT", "CANCELLED", "EXPIRED"].includes(rec.status)) return rec;
        const { action, entryPrice, stopLoss, takeProfitLevels } = rec.tradeSetup;
        const buy = action === "BUY";
        const tp2 = takeProfitLevels.find((t) => t.level === 2)?.price;
        const tp1 = takeProfitLevels.find((t) => t.level === 1)?.price;
        let status = rec.status;
        if (buy) {
          if (mid <= stopLoss) status = "STOPPED_OUT";
          else if (tp2 && mid >= tp2) status = "HIT_TP2";
          else if (tp1 && mid >= tp1) status = "HIT_TP1";
          else if (mid > entryPrice) status = "IN_PROFIT";
          else status = rec.status === "PENDING" ? "PENDING" : rec.status;
        } else if (mid >= stopLoss) status = "STOPPED_OUT";
        else if (tp2 && mid <= tp2) status = "HIT_TP2";
        else if (tp1 && mid <= tp1) status = "HIT_TP1";
        else if (mid < entryPrice) status = "IN_PROFIT";
        const risk = Math.abs(entryPrice - stopLoss) || 1;
        const pnlR = (buy ? mid - entryPrice : entryPrice - mid) / risk;
        const next = { ...rec, status, pnlPips: pnlR, pnlPercent: pnlR * 100 };
        if (
          status !== rec.status &&
          ["HIT_TP1", "HIT_TP2", "STOPPED_OUT", "EXPIRED"].includes(status)
        ) {
          void api.patchRecommendation(rec.id, { status, pnlPips: pnlR, pnlPercent: pnlR * 100 }).catch(() => undefined);
        }
        return next;
      }),
    })),
}));
