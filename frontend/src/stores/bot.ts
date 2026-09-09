"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { BotSignal, BotStatus, PreflightReport, StrategyPerf } from "@/lib/types";

type BotState = {
  status: BotStatus | null;
  signals: BotSignal[];
  performance: StrategyPerf[];
  preflight: PreflightReport | null;
  load: () => Promise<void>;
  start: (force?: boolean) => Promise<void>;
  stop: () => Promise<void>;
  promote: (id: string) => Promise<void>;
};

export const useBot = create<BotState>((set, get) => ({
  status: null,
  signals: [],
  performance: [],
  preflight: null,
  load: async () => {
    const [status, signals, perf, preflight] = await Promise.all([
      api.botStatus().catch(() => null),
      api.botSignals().then((d) => d.signals || []).catch(() => []),
      api.botPerformance().then((d) => d.performance || []).catch(() => []),
      api.botPreflight().catch(() => null),
    ]);
    set({ status, signals, performance: perf, preflight });
  },
  start: async (force = false) => {
    try {
      const status = await api.botStart(force);
      set({ status, preflight: status.preflight || get().preflight });
    } catch (err) {
      const raw = err instanceof Error ? err.message : "";
      try {
        const parsed = JSON.parse(raw) as { detail?: { preflight?: PreflightReport } };
        if (parsed.detail?.preflight) set({ preflight: parsed.detail.preflight });
      } catch {
        /* keep last preflight */
      }
      throw err;
    }
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
