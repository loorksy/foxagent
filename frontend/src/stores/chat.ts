"use client";

import { create } from "zustand";
import type {
  AgentSession,
  Artifact,
  ChatMessage,
  DebateLine,
  MemoryRecall,
  RunThought,
  RunTool,
} from "@/lib/types";
import { MODELS } from "@/lib/constants";
import { uid } from "@/lib/utils";

type ChatState = {
  messages: ChatMessage[];
  streaming: boolean;
  model: string;
  runId: string | null;
  thoughts: RunThought[];
  tools: RunTool[];
  debate: DebateLine[];
  artifacts: Artifact[];
  recalls: MemoryRecall[];
  artifactsOpen: boolean;
  artifactsWidth: number;
  activeArtifactId: string | null;
  highlight: string | null;
  setModel: (model: string) => void;
  setHighlight: (highlight: string | null) => void;
  setArtifactsOpen: (open: boolean) => void;
  setArtifactsWidth: (width: number) => void;
  setActiveArtifact: (id: string | null) => void;
  pushUser: (text: string) => string;
  startRun: (runId: string) => void;
  appendAssistant: (text: string, recommendationId?: string) => void;
  appendToken: (text: string) => void;
  appendThought: (agent: string, text: string, channel?: string) => void;
  upsertToolCall: (tool: RunTool) => void;
  upsertToolResult: (id: string, output: unknown) => void;
  addDebate: (line: DebateLine) => void;
  addRecall: (recall: MemoryRecall) => void;
  startArtifact: (artifact: Artifact) => void;
  appendArtifact: (id: string, text: string) => void;
  endArtifact: (artifact: Artifact) => void;
  complete: () => void;
  hydrateFromSession: (session: AgentSession) => void;
  loadMessages: (messages: ChatMessage[]) => void;
  clearChat: () => void;
};

function asMessages(raw: unknown): ChatMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item, index) => {
      const row = item as Partial<ChatMessage> & { content?: string };
      const text = String(row.text || row.content || "");
      const role = row.role === "assistant" || row.role === "system" ? row.role : "user";
      return {
        id: row.id || `msg_${index}`,
        role,
        text,
        createdAt: Number(row.createdAt || Date.now()),
        recommendationId: row.recommendationId,
      } satisfies ChatMessage;
    })
    .filter((m) => m.text || m.recommendationId);
}

export const useChat = create<ChatState>((set) => ({
  messages: [],
  streaming: false,
  model: MODELS[0].id,
  runId: null,
  thoughts: [],
  tools: [],
  debate: [],
  artifacts: [],
  recalls: [],
  artifactsOpen: false,
  artifactsWidth: 420,
  activeArtifactId: null,
  highlight: null,
  setModel: (model) => set({ model }),
  setHighlight: (highlight) => set({ highlight }),
  setArtifactsOpen: (artifactsOpen) => set({ artifactsOpen }),
  setArtifactsWidth: (artifactsWidth) => set({ artifactsWidth: Math.min(720, Math.max(280, artifactsWidth)) }),
  setActiveArtifact: (activeArtifactId) => set({ activeArtifactId, artifactsOpen: true }),
  pushUser: (text) => {
    const id = uid("usr");
    set((s) => ({
      messages: [...s.messages, { id, role: "user", text, createdAt: Date.now() }],
    }));
    return id;
  },
  startRun: (runId) =>
    set((s) => ({
      runId,
      streaming: true,
      thoughts: [],
      tools: [],
      debate: [],
      recalls: [],
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
  appendThought: (agent, text, channel) =>
    set((s) => {
      const last = s.thoughts[s.thoughts.length - 1];
      if (last && last.agent === agent && last.channel === channel) {
        const merged = { ...last, text: (last.text + text).slice(-12000) };
        return { thoughts: [...s.thoughts.slice(0, -1), merged] };
      }
      return { thoughts: [...s.thoughts, { agent, text, channel }] };
    }),
  upsertToolCall: (tool) =>
    set((s) => {
      const idx = s.tools.findIndex((t) => t.id && t.id === tool.id);
      if (idx >= 0) {
        const tools = s.tools.slice();
        tools[idx] = { ...tools[idx], ...tool };
        return { tools };
      }
      return { tools: [...s.tools, tool] };
    }),
  upsertToolResult: (id, output) =>
    set((s) => ({
      tools: s.tools.map((t) => (t.id === id ? { ...t, output } : t)),
    })),
  addDebate: (line) => set((s) => ({ debate: [...s.debate, line] })),
  addRecall: (recall) => set((s) => ({ recalls: [...s.recalls, recall] })),
  startArtifact: (artifact) =>
    set((s) => ({
      artifacts: [...s.artifacts.filter((a) => a.id !== artifact.id), artifact],
      artifactsOpen: true,
      activeArtifactId: artifact.id,
    })),
  appendArtifact: (id, text) =>
    set((s) => ({
      artifacts: s.artifacts.map((a) => (a.id === id ? { ...a, body: (a.body || "") + text } : a)),
    })),
  endArtifact: (artifact) =>
    set((s) => ({
      artifacts: s.artifacts.map((a) => (a.id === artifact.id ? { ...a, ...artifact } : a)),
      artifactsOpen: true,
      activeArtifactId: artifact.id,
    })),
  complete: () =>
    set((s) => ({
      streaming: false,
      messages: s.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
    })),
  hydrateFromSession: (session) => {
    const state = session.state || {};
    set({
      messages: asMessages(state.messages),
      thoughts: state.thoughts || [],
      tools: state.tools || [],
      debate: state.debate || [],
      artifacts: state.artifacts || [],
      recalls: state.recalls || [],
      streaming: false,
      runId: null,
      activeArtifactId: state.artifacts?.[0]?.id || null,
    });
  },
  loadMessages: (messages) => set({ messages, streaming: false }),
  clearChat: () =>
    set({
      messages: [],
      streaming: false,
      thoughts: [],
      tools: [],
      debate: [],
      artifacts: [],
      recalls: [],
      runId: null,
      activeArtifactId: null,
    }),
}));
