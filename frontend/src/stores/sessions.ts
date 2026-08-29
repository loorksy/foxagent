"use client";

import { create } from "zustand";
import type { ChatMessage } from "@/lib/types";
import { uid } from "@/lib/utils";
import { t } from "@/i18n";
import { useChat } from "./chat";

export type ChatSession = {
  id: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
};

const LS = "foxagent_chats_v1";

function readAll(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(LS);
    return raw ? (JSON.parse(raw) as ChatSession[]) : [];
  } catch {
    return [];
  }
}

function writeAll(sessions: ChatSession[]) {
  try {
    localStorage.setItem(LS, JSON.stringify(sessions));
  } catch {
    /* ignore */
  }
}

type SessionsState = {
  sessions: ChatSession[];
  activeId: string | null;
  query: string;
  hydrate: () => void;
  setQuery: (query: string) => void;
  newChat: () => void;
  openChat: (id: string) => void;
  removeChat: (id: string) => void;
  persistActive: (messages: ChatMessage[]) => void;
};

function titleFrom(messages: ChatMessage[]) {
  const first = messages.find((m) => m.role === "user");
  return first?.text.trim().slice(0, 42) || t("chats.untitled");
}

export const useSessions = create<SessionsState>((set, get) => ({
  sessions: [],
  activeId: null,
  query: "",
  hydrate: () => set({ sessions: readAll() }),
  setQuery: (query) => set({ query }),
  newChat: () => {
    useChat.getState().clearChat();
    set({ activeId: null });
  },
  openChat: (id) => {
    const session = get().sessions.find((s) => s.id === id);
    if (!session) return;
    useChat.getState().loadMessages(session.messages);
    set({ activeId: id });
  },
  removeChat: (id) => {
    const sessions = get().sessions.filter((s) => s.id !== id);
    writeAll(sessions);
    if (get().activeId === id) {
      useChat.getState().clearChat();
      set({ sessions, activeId: null });
      return;
    }
    set({ sessions });
  },
  persistActive: (messages) => {
    if (!messages.length) return;
    const { sessions, activeId } = get();
    const now = Date.now();
    if (activeId) {
      const next = sessions.map((s) =>
        s.id === activeId ? { ...s, messages, title: titleFrom(messages), updatedAt: now } : s
      );
      writeAll(next);
      set({ sessions: next });
      return;
    }
    const created: ChatSession = {
      id: uid("chat"),
      title: titleFrom(messages),
      updatedAt: now,
      messages,
    };
    const next = [created, ...sessions];
    writeAll(next);
    set({ sessions: next, activeId: created.id });
  },
}));
