"use client";

import { create } from "zustand";
import type { AgentSession, ChatMessage } from "@/lib/types";
import { api } from "@/lib/api";
import { t } from "@/i18n";
import { useChat } from "./chat";
import { useWorkspace } from "./workspace";

export type ChatSession = {
  id: string;
  title: string;
  updatedAt: number;
  symbol: string;
  timeframe: string;
  raw?: AgentSession;
};

type SessionsState = {
  sessions: ChatSession[];
  activeId: string | null;
  query: string;
  hydrate: () => Promise<void>;
  setQuery: (query: string) => void;
  setActiveId: (id: string | null) => void;
  openSession: (id: string) => Promise<void>;
  ensureSession: (id: string) => Promise<AgentSession>;
  removeChat: (id: string) => Promise<void>;
  persistActive: (messages: ChatMessage[]) => void;
};

function toCard(item: AgentSession): ChatSession {
  const updated = item.updatedAt ? Date.parse(item.updatedAt) : Date.now();
  return {
    id: item.id,
    title: item.title || t("chats.untitled"),
    updatedAt: Number.isFinite(updated) ? updated : Date.now(),
    symbol: item.symbol,
    timeframe: item.timeframe,
    raw: item,
  };
}

function titleFrom(messages: ChatMessage[]) {
  const first = messages.find((m) => m.role === "user");
  return first?.text.trim().slice(0, 42) || t("chats.untitled");
}

export const useSessions = create<SessionsState>((set, get) => ({
  sessions: [],
  activeId: null,
  query: "",
  hydrate: async () => {
    try {
      const data = await api.sessions();
      set({ sessions: (data.sessions || []).map(toCard) });
    } catch {
      /* backend may still be booting */
    }
  },
  setQuery: (query) => set({ query }),
  setActiveId: (activeId) => set({ activeId }),
  openSession: async (id) => {
    const item = await get().ensureSession(id);
    useChat.getState().hydrateFromSession(item);
    if (item.symbol) useWorkspace.getState().setSymbol(item.symbol);
    if (item.timeframe) useWorkspace.getState().setTimeframe(item.timeframe);
    const overlays = item.state?.overlays;
    if (overlays?.length) useWorkspace.getState().applyToChart(overlays, null, item.state?.recommendationId || undefined);
    set((s) => ({
      activeId: id,
      sessions: s.sessions.some((x) => x.id === id)
        ? s.sessions.map((x) => (x.id === id ? toCard(item) : x))
        : [toCard(item), ...s.sessions],
    }));
  },
  ensureSession: async (id) => {
    try {
      return await api.getSession(id);
    } catch {
      return api.createSession({ id });
    }
  },
  removeChat: async (id) => {
    try {
      await api.deleteSession(id);
    } catch {
      /* already gone */
    }
    const sessions = get().sessions.filter((s) => s.id !== id);
    if (get().activeId === id) {
      useChat.getState().clearChat();
      set({ sessions, activeId: null });
      return;
    }
    set({ sessions });
  },
  persistActive: (messages) => {
    const { activeId, sessions } = get();
    if (!activeId || !messages.length) return;
    const title = titleFrom(messages);
    const next = sessions.map((s) => (s.id === activeId ? { ...s, title, updatedAt: Date.now() } : s));
    set({ sessions: next });
    const chat = useChat.getState();
    const command = useWorkspace.getState().command;
    void api
      .saveSession(activeId, {
        title,
        state: {
          artifacts: chat.artifacts,
          overlays: command?.type === "apply" ? command.overlays : [],
          recommendationId: messages.find((m) => m.recommendationId)?.recommendationId || null,
        },
      })
      .catch(() => undefined);
  },
}));
