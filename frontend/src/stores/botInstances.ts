"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { BotInstance, BotInstanceCreatePayload } from "@/lib/types";

type BotInstancesState = {
  instances: BotInstance[];
  paused: boolean;
  loading: boolean;
  error: string;
  load: () => Promise<void>;
  create: (body: BotInstanceCreatePayload) => Promise<BotInstance | null>;
  patch: (id: string, body: Record<string, unknown>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  start: (id: string) => Promise<void>;
  stop: (id: string) => Promise<void>;
};

function asInstance(raw: unknown): BotInstance | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as BotInstance;
  if (!row.id || !row.name) return null;
  return {
    ...row,
    stats: row.stats || { cycles: 0, lastError: "", lastSignalAt: null },
    agents: row.agents || [],
    strategyIds: row.strategyIds || [],
    allowedSessions: row.allowedSessions || [],
  };
}

function parseError(err: unknown): string {
  if (!(err instanceof Error)) return "request failed";
  const text = err.message.trim();
  if (!text) return "request failed";
  try {
    const parsed = JSON.parse(text) as { detail?: string };
    if (parsed.detail) return parsed.detail;
  } catch {
    /* plain text from backend */
  }
  return text;
}

export const useBotInstances = create<BotInstancesState>((set, get) => ({
  instances: [],
  paused: false,
  loading: false,
  error: "",
  load: async () => {
    set({ loading: true, error: "" });
    try {
      const data = await api.botInstances();
      set({
        instances: (data.instances || []).map(asInstance).filter((r): r is BotInstance => Boolean(r)),
        paused: Boolean(data.paused),
        loading: false,
      });
    } catch (err) {
      set({ loading: false, error: parseError(err) });
    }
  },
  create: async (body) => {
    set({ error: "" });
    try {
      const data = await api.createBotInstance(body);
      await get().load();
      return asInstance(data);
    } catch (err) {
      set({ error: parseError(err) });
      return null;
    }
  },
  patch: async (id, body) => {
    set({ error: "" });
    try {
      await api.patchBotInstance(id, body);
      await get().load();
    } catch (err) {
      set({ error: parseError(err) });
    }
  },
  remove: async (id) => {
    set({ error: "" });
    try {
      await api.deleteBotInstance(id);
      await get().load();
    } catch (err) {
      set({ error: parseError(err) });
    }
  },
  start: async (id) => {
    set({ error: "" });
    try {
      await api.startBotInstance(id);
      await get().load();
    } catch (err) {
      set({ error: parseError(err) });
    }
  },
  stop: async (id) => {
    set({ error: "" });
    try {
      await api.stopBotInstance(id);
      await get().load();
    } catch (err) {
      set({ error: parseError(err) });
    }
  },
}));
