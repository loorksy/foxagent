"use client";

import { create } from "zustand";
import type { AgentPhase, ChatMessage } from "@/lib/types";
import { MODELS } from "@/lib/constants";
import { uid } from "@/lib/utils";

const IDLE_PHASES: AgentPhase[] = [
  { id: 1, name: "Fetching OANDA Candles (1D, 4H, 15M)", detail: "Multi-timeframe OHLCV ingest", status: "pending" },
  { id: 2, name: "Visual Chart Inspection & Liquidity Mapping", detail: "Claude Vision + ICT structure", status: "pending" },
  { id: 3, name: "Macro & Sentiment Ingestion", detail: "Session liquidity, HTF bias, confluence", status: "pending" },
  { id: 4, name: "Synthesizing Recommendation & Chart Annotations", detail: "Overlays, entry, SL, TP", status: "pending" },
];

type ChatState = {
  messages: ChatMessage[];
  phases: AgentPhase[];
  streaming: boolean;
  model: string;
  runId: string | null;
  thoughts: string[];
  setModel: (model: string) => void;
  pushUser: (text: string) => string;
  startRun: (runId: string, phases?: AgentPhase[]) => void;
  appendAssistant: (text: string, recommendationId?: string) => void;
  appendToken: (text: string) => void;
  setPhase: (phase: AgentPhase) => void;
  addThought: (text: string) => void;
  complete: () => void;
  resetPhases: () => void;
};

export const useChat = create<ChatState>((set) => ({
  messages: [
    {
      id: "sys_welcome",
      role: "system",
      text: "FoxAgent online. Multi-timeframe ICT desk is armed. Pick a pair, then /scan or Generate Setup.",
      createdAt: Date.now(),
    },
  ],
  phases: IDLE_PHASES,
  streaming: false,
  model: MODELS[0].id,
  runId: null,
  thoughts: [],
  setModel: (model) => set({ model }),
  pushUser: (text) => {
    const id = uid("usr");
    set((s) => ({
      messages: [...s.messages, { id, role: "user", text, createdAt: Date.now() }],
    }));
    return id;
  },
  startRun: (runId, phases) =>
    set((s) => ({
      runId,
      streaming: true,
      thoughts: [],
      phases: (phases || IDLE_PHASES).map((p, i) => ({ ...p, status: i === 0 ? "active" : "pending" })),
      messages: [
        ...s.messages,
        { id: uid("ast"), role: "assistant", text: "", createdAt: Date.now(), streaming: true },
      ],
    })),
  appendAssistant: (text, recommendationId) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = [...msgs].reverse().find((m) => m.role === "assistant");
      if (last && (last.streaming || !last.text)) {
        return {
          messages: msgs.map((m) =>
            m.id === last.id ? { ...m, text: text || m.text, recommendationId, streaming: false } : m
          ),
        };
      }
      return {
        messages: [...msgs, { id: uid("ast"), role: "assistant", text, createdAt: Date.now(), recommendationId }],
      };
    }),
  appendToken: (text) =>
    set((s) => {
      const msgs = [...s.messages];
      const idx = [...msgs].reverse().findIndex((m) => m.role === "assistant" && m.streaming);
      if (idx === -1) return s;
      const real = msgs.length - 1 - idx;
      msgs[real] = { ...msgs[real], text: msgs[real].text + text };
      return { messages: msgs };
    }),
  setPhase: (phase) =>
    set((s) => ({
      phases: s.phases.map((p) => (p.id === phase.id ? { ...p, ...phase } : p)),
    })),
  addThought: (text) =>
    set((s) => ({ thoughts: [...s.thoughts.slice(-24), text].filter(Boolean) })),
  complete: () =>
    set((s) => ({
      streaming: false,
      messages: s.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
      phases: s.phases.map((p) => (p.status === "active" ? { ...p, status: "complete" } : p)),
    })),
  resetPhases: () => set({ phases: IDLE_PHASES, thoughts: [] }),
}));
