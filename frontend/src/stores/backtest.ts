"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { BacktestReport } from "@/lib/types";

type BacktestState = {
  report: BacktestReport | null;
  history: BacktestReport[];
  running: boolean;
  error: string;
  run: (body: {
    timeframe: string;
    strategyId: string | null;
    days: number;
    riskPercent?: number;
    minRr?: number;
  }) => Promise<void>;
  loadHistory: () => Promise<void>;
};

export const useBacktest = create<BacktestState>((set) => ({
  report: null,
  history: [],
  running: false,
  error: "",
  run: async (body) => {
    set({ running: true, error: "" });
    try {
      const report = await api.runBacktest(body);
      set({ report, running: false });
    } catch (err) {
      set({ running: false, error: err instanceof Error ? err.message : "backtest failed" });
    }
  },
  loadHistory: async () => {
    try {
      const data = await api.backtestReports();
      set({ history: data.reports || [] });
    } catch {
      set({ history: [] });
    }
  },
}));
