"use client";

import { create } from "zustand";
import type {
  AgentSession,
  Artifact,
  ChatImage,
  ChatMessage,
  DebateLine,
  MemoryRecall,
  RunStep,
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
  steps: RunStep[];
  runStartedAt: number | null;
  runEndedAt: number | null;
  runIntent: string | null;
  artifacts: Artifact[];
  recalls: MemoryRecall[];
  artifactsOpen: boolean;
  artifactsWidth: number;
  activeArtifactId: string | null;
  highlight: string | null;
  abort: AbortController | null;
  runUsage: TokenUsage | null;
  sessionUsage: TokenUsage | null;
  queuedText: string | null;
  setModel: (model: string) => void;
  queueMessage: (text: string) => void;
  clearQueue: () => void;
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
  upsertToolResult: (id: string, output: unknown, name?: string) => void;
  attachImage: (image: ChatImage) => void;
  addDebate: (line: DebateLine) => void;
  addRecall: (recall: MemoryRecall) => void;
  setIntent: (intent: string) => void;
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
        images: Array.isArray(row.images) ? row.images : undefined,
        steps: Array.isArray(row.steps) ? row.steps : undefined,
      } satisfies ChatMessage;
    })
    .filter((m) => m.text || m.recommendationId || m.strategyProposal || m.strategyExperiment || (m.images && m.images.length) || (m.steps && m.steps.length));
}

export const useChat = create<ChatState>((set) => ({
  messages: [],
  streaming: false,
  model: MODELS[0].id,
  runId: null,
  thoughts: [],
  tools: [],
  debate: [],
  steps: [],
  runStartedAt: null,
  runEndedAt: null,
  runIntent: null,
  artifacts: [],
  recalls: [],
  artifactsOpen: false,
  artifactsWidth: 420,
  activeArtifactId: null,
  highlight: null,
  abort: null,
  runUsage: null,
  sessionUsage: null,
  queuedText: null,
  setModel: (model) => set({ model }),
  queueMessage: (text) => set({ queuedText: text.trim() || null }),
  clearQueue: () => set({ queuedText: null }),
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
      steps: [],
      recalls: [],
      runStartedAt: Date.now(),
      runEndedAt: null,
      runIntent: null,
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
      const lastThought = s.thoughts[s.thoughts.length - 1];
      const thoughts =
        lastThought && lastThought.agent === agent && lastThought.channel === channel
          ? [...s.thoughts.slice(0, -1), { ...lastThought, text: (lastThought.text + text).slice(-12000) }]
          : [...s.thoughts, { agent, text, channel }];
      const lastStep = s.steps[s.steps.length - 1];
      const steps =
        lastStep && lastStep.kind === "thought" && lastStep.agent === agent && lastStep.channel === channel
          ? [...s.steps.slice(0, -1), { ...lastStep, text: ((lastStep.text || "") + text).slice(-12000) }]
          : [...s.steps, { kind: "thought" as const, agent, text, channel, at: Date.now() }];
      return { thoughts, steps };
    }),
  upsertToolCall: (tool) =>
    set((s) => {
      const idx = s.tools.findIndex((t) => t.id && t.id === tool.id);
      const tools = idx >= 0 ? s.tools.map((t, i) => (i === idx ? { ...t, ...tool } : t)) : [...s.tools, tool];
      const stepIdx = s.steps.findIndex((st) => st.kind === "tool" && st.toolId && st.toolId === tool.id);
      const steps =
        stepIdx >= 0
          ? s.steps.map((st, i) =>
              i === stepIdx
                ? {
                    ...st,
                    toolName: tool.name,
                    toolLabel: tool.label || st.toolLabel,
                    toolInput: tool.input,
                    agent: tool.agent,
                  }
                : st
            )
          : [
              ...s.steps,
              {
                kind: "tool" as const,
                agent: tool.agent,
                toolId: tool.id,
                toolName: tool.name,
                toolLabel: tool.label,
                toolInput: tool.input,
                at: Date.now(),
              },
            ];
      return { tools, steps };
    }),
  upsertToolResult: (id, output, name) =>
    set((s) => {
      const toolHit =
        s.tools.find((t) => Boolean(id) && t.id === id) ||
        s.tools.find((t) => Boolean(name) && t.name === name && t.output == null);
      const stepHit =
        s.steps.find((st) => st.kind === "tool" && Boolean(id) && st.toolId === id) ||
        s.steps.find((st) => st.kind === "tool" && st.toolOutput == null && Boolean(name) && st.toolName === name);
      return {
        tools: s.tools.map((t) => (toolHit && t.id === toolHit.id ? { ...t, output } : t)),
        steps: s.steps.map((st) => (stepHit && st === stepHit ? { ...st, toolOutput: output } : st)),
      };
    }),
  attachImage: (image) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = [...msgs].reverse().find((m) => m.role === "assistant");
      if (!last) {
        return {
          messages: [...msgs, { id: uid("ast"), role: "assistant", text: "", createdAt: Date.now(), images: [image] }],
        };
      }
      const images = [...(last.images || []).filter((x) => x.id !== image.id), image];
      return { messages: msgs.map((m) => (m.id === last.id ? { ...m, images } : m)) };
    }),
  addDebate: (line) =>
    set((s) => ({
      debate: [...s.debate, line],
      steps: [...s.steps, { kind: "debate" as const, agent: line.agent, role: line.role, text: line.text, at: Date.now() }],
    })),
  addRecall: (recall) =>
    set((s) => ({
      recalls: [...s.recalls, recall],
      steps: [
        ...s.steps,
        { kind: "recall" as const, text: recall.text || (recall.lessons || []).join("\n"), at: Date.now() },
      ],
    })),
  setIntent: (intent) =>
    set((s) => ({
      runIntent: intent,
      steps: [...s.steps, { kind: "intent" as const, intent, at: Date.now() }],
    })),
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
    set((s) => {
      const steps = s.steps.map((st) =>
        st.kind === "tool" && st.toolOutput == null ? { ...st, toolOutput: { ok: true } } : st
      );
      return {
        streaming: false,
        runEndedAt: s.streaming ? Date.now() : s.runEndedAt,
        sessionUsage: s.streaming ? addUsage(s.sessionUsage, s.runUsage) : s.sessionUsage,
        steps,
        tools: s.tools.map((t) => (t.output == null ? { ...t, output: { ok: true } } : t)),
        messages: s.messages.map((m) => (m.streaming ? { ...m, streaming: false, steps } : m)),
      };
    }),
  hydrateFromSession: (session) => {
    const state = session.state || {};
    const messages = asMessages(state.messages);
    const sessionUsage = messages.reduce<TokenUsage | null>((acc, m) => (m.usage ? addUsage(acc, m.usage) : acc), null);
    const steps: RunStep[] = [
      ...(state.recalls || []).map((r) => ({
        kind: "recall" as const,
        text: r.text || (r.lessons || []).join("\n"),
        at: 0,
      })),
      ...(state.thoughts || []).map((th) => ({
        kind: "thought" as const,
        agent: th.agent,
        text: th.text,
        channel: th.channel,
        at: 0,
      })),
      ...(state.tools || []).map((tool) => ({
        kind: "tool" as const,
        agent: tool.agent,
        toolId: tool.id,
        toolName: tool.name,
        toolLabel: tool.label,
        toolInput: tool.input,
        toolOutput: tool.output,
        at: 0,
      })),
      ...(state.debate || []).map((d) => ({
        kind: "debate" as const,
        agent: d.agent,
        role: d.role,
        text: d.text,
        at: 0,
      })),
    ];
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    const hydrated = lastAssistant && !lastAssistant.steps?.length && steps.length
      ? messages.map((m) => (m.id === lastAssistant.id ? { ...m, steps } : m))
      : messages;
    set({
      messages: hydrated,
      thoughts: state.thoughts || [],
      tools: state.tools || [],
      debate: state.debate || [],
      steps,
      runStartedAt: null,
      runEndedAt: null,
      runIntent: null,
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
      steps: [],
      runStartedAt: null,
      runEndedAt: null,
      runIntent: null,
      artifacts: [],
      recalls: [],
      runId: null,
      runUsage: null,
      sessionUsage: null,
      queuedText: null,
      activeArtifactId: null,
    }),
}));
