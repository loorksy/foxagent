"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { BotSignal, BotStatus, StrategyPerf } from "@/lib/types";

type BotState = {
  status: BotStatus | null;
  signals: BotSignal[];
  performance: StrategyPerf[];
  load: () => Promise<void>;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  promote: (id: string) => Promise<void>;
};

export const useBot = create<BotState>((set, get) => ({
  status: null,
  signals: [],
  performance: [],
  load: async () => {
    const [status, signals, perf] = await Promise.all([
      api.botStatus().catch(() => null),
      api.botSignals().then((d) => d.signals || []).catch(() => []),
      api.botPerformance().then((d) => d.performance || []).catch(() => []),
    ]);
    set({ status, signals, performance: perf });
  },
  start: async () => {
    const status = await api.botStart();
    set({ status });
    await get().load();
  },
  stop: async () => {
    const status = await api.botStop();
    set({ status });
  },
  promote: async (id: string) => {
    await api.promoteBotSignal(id);
    await get().load();
  },
}));
