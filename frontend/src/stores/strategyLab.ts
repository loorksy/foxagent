"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { StrategyRule, StrategyValidation } from "@/lib/types";

type LabTab = "library" | "create" | "proposed" | "results" | "jobs" | "leaderboard";

type StrategyLabState = {
  items: StrategyRule[];
  lastValidation: StrategyValidation | null;
  history: StrategyValidation[];
  loading: boolean;
  error: string;
  tab: LabTab;
  setTab: (tab: LabTab) => void;
  load: () => Promise<void>;
  create: (body: Record<string, unknown>) => Promise<StrategyRule | null>;
  patch: (id: string, body: Record<string, unknown>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  validate: (id: string, autoActivate?: boolean) => Promise<StrategyValidation | null>;
  approve: (id: string) => Promise<void>;
  reject: (id: string, reason?: string) => Promise<void>;
  pin: (id: string) => Promise<void>;
  unpin: (id: string) => Promise<void>;
};

function asRule(raw: unknown): StrategyRule | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as StrategyRule;
  if (!row.id || !row.name) return null;
  return {
    ...row,
    timeframes: row.timeframes?.length ? row.timeframes : row.timeframe || ["M15"],
    entry_conditions: row.entry_conditions || {},
  };
}

export const useStrategyLab = create<StrategyLabState>((set, get) => ({
  items: [],
  lastValidation: null,
  history: [],
  loading: false,
  error: "",
  tab: "library",
  setTab: (tab) => set({ tab }),
  load: async () => {
    set({ loading: true, error: "" });
    try {
      const data = await api.strategies();
      set({ items: (data.strategies || []).map(asRule).filter((r): r is StrategyRule => Boolean(r)), loading: false });
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : "load failed" });
    }
  },
  create: async (body) => {
    set({ error: "" });
    try {
      const data = await api.createStrategy(body);
      const rule = asRule(data.strategy);
      await get().load();
      return rule;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "create failed" });
      return null;
    }
  },
  patch: async (id, body) => {
    set({ error: "" });
    try {
      await api.patchStrategy(id, body);
      await get().load();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "patch failed" });
    }
  },
  remove: async (id) => {
    set({ error: "" });
    try {
      await api.deleteStrategy(id);
      await get().load();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "delete failed" });
    }
  },
  validate: async (id) => {
    set({ error: "" });
    try {
      const result = await api.validateStrategy(id, { days: 730 });
      set((s) => ({ lastValidation: result, history: [result, ...s.history].slice(0, 12) }));
      await get().load();
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "validate failed";
      set({ error: message });
      return null;
    }
  },
  approve: async (id) => {
    set({ error: "" });
    try {
      await api.approveStrategy(id);
      await get().load();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "approve failed" });
    }
  },
  reject: async (id, reason = "") => {
    set({ error: "" });
    try {
      await api.rejectStrategy(id, reason);
      await get().load();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "reject failed" });
    }
  },
  pin: async (id) => {
    try {
      await api.pinStrategy(id);
      await get().load();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "pin failed" });
    }
  },
  unpin: async (id) => {
    try {
      await api.unpinStrategy(id);
      await get().load();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "unpin failed" });
    }
  },
}));
