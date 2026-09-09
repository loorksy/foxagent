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
  StrategyExperimentJob,
  StrategyRule,
  StrategyValidation,
  TokenUsage,
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
  abort: AbortController | null;
  runUsage: TokenUsage | null;
  sessionUsage: TokenUsage | null;
  setModel: (model: string) => void;
  setHighlight: (highlight: string | null) => void;
  setArtifactsOpen: (open: boolean) => void;
  setArtifactsWidth: (width: number) => void;
  setActiveArtifact: (id: string | null) => void;
  pushUser: (text: string) => string;
  startRun: (runId: string) => void;
  appendAssistant: (text: string, recommendationId?: string) => void;
  attachStrategyProposal: (proposal: StrategyRule) => void;
  attachStrategyValidation: (validation: StrategyValidation) => void;
  attachStrategyExperiment: (job: StrategyExperimentJob) => void;
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
  applyUsage: (usage: TokenUsage) => void;
  hydrateFromSession: (session: AgentSession) => void;
  loadMessages: (messages: ChatMessage[]) => void;
  clearChat: () => void;
};

function emptyUsage(): TokenUsage {
  return { inputTokens: 0, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 0, totalTokens: 0, estimatedUsd: 0, calls: 0 };
}

function addUsage(a: TokenUsage | null | undefined, b: TokenUsage | null | undefined): TokenUsage {
  const left = a || emptyUsage();
  const right = b || emptyUsage();
  return {
    inputTokens: (left.inputTokens || 0) + (right.inputTokens || 0),
    outputTokens: (left.outputTokens || 0) + (right.outputTokens || 0),
    cacheCreationTokens: (left.cacheCreationTokens || 0) + (right.cacheCreationTokens || 0),
    cacheReadTokens: (left.cacheReadTokens || 0) + (right.cacheReadTokens || 0),
    totalTokens: (left.totalTokens || 0) + (right.totalTokens || 0),
    estimatedUsd: Number(((left.estimatedUsd || 0) + (right.estimatedUsd || 0)).toFixed(4)),
    calls: (left.calls || 0) + (right.calls || 0),
    model: right.model || left.model,
  };
}

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
        strategyProposal: row.strategyProposal,
        strategyValidation: row.strategyValidation,
        strategyExperiment: row.strategyExperiment,
        usage: row.usage,
      } satisfies ChatMessage;
    })
    .filter((m) => m.text || m.recommendationId || m.strategyProposal || m.strategyExperiment);
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
  abort: null,
  runUsage: null,
  sessionUsage: null,
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
      runUsage: null,
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
  attachStrategyProposal: (proposal) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = [...msgs].reverse().find((m) => m.role === "assistant");
      if (!last) {
        return {
          messages: [...msgs, { id: uid("ast"), role: "assistant", text: "", createdAt: Date.now(), strategyProposal: proposal }],
        };
      }
      return { messages: msgs.map((m) => (m.id === last.id ? { ...m, strategyProposal: proposal } : m)) };
    }),
  attachStrategyValidation: (validation) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = [...msgs].reverse().find((m) => m.role === "assistant");
      if (!last) return s;
      return { messages: msgs.map((m) => (m.id === last.id ? { ...m, strategyValidation: validation } : m)) };
    }),
  attachStrategyExperiment: (job) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = [...msgs].reverse().find((m) => m.role === "assistant");
      if (!last) {
        return {
          messages: [...msgs, { id: uid("ast"), role: "assistant", text: "", createdAt: Date.now(), strategyExperiment: job }],
        };
      }
      return { messages: msgs.map((m) => (m.id === last.id ? { ...m, strategyExperiment: job } : m)) };
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
  applyUsage: (usage) =>
    set((s) => {
      const msgs = s.messages.map((m) =>
        m.role === "assistant" && (m.streaming || m.id === s.messages.filter((x) => x.role === "assistant").at(-1)?.id)
          ? { ...m, usage }
          : m
      );
      return { runUsage: usage, messages: msgs };
    }),
  complete: () =>
    set((s) => ({
      streaming: false,
      sessionUsage: s.streaming ? addUsage(s.sessionUsage, s.runUsage) : s.sessionUsage,
      messages: s.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
    })),
  hydrateFromSession: (session) => {
    const state = session.state || {};
    const messages = asMessages(state.messages);
    const sessionUsage = messages.reduce<TokenUsage | null>((acc, m) => (m.usage ? addUsage(acc, m.usage) : acc), null);
    set({
      messages,
      thoughts: state.thoughts || [],
      tools: state.tools || [],
      debate: state.debate || [],
      artifacts: state.artifacts || [],
      recalls: state.recalls || [],
      streaming: false,
      runId: null,
      runUsage: null,
      sessionUsage,
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
      runUsage: null,
      sessionUsage: null,
      activeArtifactId: null,
    }),
}));
