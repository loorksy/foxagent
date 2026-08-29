"use client";

import { create } from "zustand";
import type { KlineOverlay, LivePrice } from "@/lib/types";
import { PERIODS } from "@/lib/constants";

type Period = (typeof PERIODS)[number];

type ChartCommand =
  | { type: "apply"; overlays: KlineOverlay[]; focusTimestamp?: number | null; recId?: string }
  | { type: "clear" }
  | { type: "focus"; timestamp: number };

type WorkspaceState = {
  symbol: string;
  period: Period;
  prices: Record<string, LivePrice>;
  dataMode: "oanda" | "simulator";
  chartNonce: number;
  chartOpen: boolean;
  command: ChartCommand | null;
  setChartOpen: (open: boolean) => void;
  toggleChart: () => void;
  setSymbol: (symbol: string) => void;
  setPeriod: (period: Period) => void;
  setTimeframe: (text: string) => void;
  setPrice: (price: LivePrice) => void;
  setDataMode: (mode: "oanda" | "simulator") => void;
  applyToChart: (overlays: KlineOverlay[], focusTimestamp?: number | null, recId?: string) => void;
  clearOverlays: () => void;
  focusTimestamp: (timestamp: number) => void;
};

export const useWorkspace = create<WorkspaceState>((set) => ({
  symbol: "XAU_USD",
  period: PERIODS[2],
  prices: {},
  dataMode: "simulator",
  chartNonce: 0,
  chartOpen: false,
  command: null,
  setChartOpen: (chartOpen) => set({ chartOpen }),
  toggleChart: () => set((s) => ({ chartOpen: !s.chartOpen })),
  setSymbol: (symbol) => set({ symbol, chartNonce: Date.now() }),
  setPeriod: (period) => set({ period }),
  setTimeframe: (text) =>
    set((s) => {
      const period = PERIODS.find((p) => p.text.toLowerCase() === text.toLowerCase() || p.granularity.toLowerCase() === text.toLowerCase());
      return period ? { period } : s;
    }),
  setPrice: (price) =>
    set((s) => ({ prices: { ...s.prices, [price.instrument]: price } })),
  setDataMode: (dataMode) => set({ dataMode }),
  applyToChart: (overlays, focusTimestamp, recId) =>
    set({
      command: { type: "apply", overlays, focusTimestamp, recId },
      chartOpen: true,
    }),
  clearOverlays: () => set({ command: { type: "clear" } }),
  focusTimestamp: (timestamp) => set({ command: { type: "focus", timestamp }, chartOpen: true }),
}));
