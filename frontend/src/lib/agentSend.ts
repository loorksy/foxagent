import { MODELS, QUICK_PROMPTS, parsePairShortcut } from "@/lib/constants";
import { api } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace";
import { useChat } from "@/stores/chat";
import { useCatalog } from "@/stores/catalog";
import { useRecommendations } from "@/stores/recommendations";
import { useSessions } from "@/stores/sessions";
import type { Artifact, KlineOverlay, StructureScan, TradeRecommendation } from "@/lib/types";
import { t } from "@/i18n";

const SETUP_PROMPT = QUICK_PROMPTS.find((q) => q.id === "setup")?.prompt || "Generate a complete ICT trade setup.";

function formatStructure(symbol: string, tf: string, data: StructureScan): string {
  const lines = [
    t("chat.scanTitle", { symbol, tf }),
    t("chat.scanBias", { bias: data.bias || "—" }),
    `BOS: ${data.lastBos || "—"}`,
    `FVG: ${data.fvgCount ?? 0}`,
    `Order blocks: ${data.orderBlocks ?? 0}`,
    `Sweep: ${data.liquiditySweep || "—"}`,
  ];
  if (data.confluence?.length) {
    lines.push(`Confluence: ${data.confluence.join("; ")}`);
  }
  return lines.join("\n");
}

function fvgOverlays(data: StructureScan): KlineOverlay[] {
  return (data.fvgs || []).map((fvg, index) => ({
    name: "rect",
    id: `scan-fvg-${index}`,
    points: [
      { timestamp: fvg.timestampStart, value: fvg.high },
      { timestamp: fvg.timestampEnd, value: fvg.low },
    ],
    styles: {
      fillColor: fvg.direction === "bullish" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
      borderColor: fvg.direction === "bullish" ? "#22c55e" : "#ef4444",
    },
  }));
}

export async function sendAgentMessage(raw: string) {
  const text = raw.trim();
  const streaming = useChat.getState().streaming;
  if (!text || streaming) return;

  const workspace = useWorkspace.getState();
  const chat = useChat.getState();
  let message = text;

  if (text.startsWith("/")) {
    const [cmd, ...rest] = text.slice(1).split(/\s+/);
    const arg = rest.join(" ");
    if (cmd === "pair" || cmd === "symbol") {
      const parsed = parsePairShortcut(arg);
      if (parsed) workspace.setSymbol(parsed);
      return;
    }
    if (cmd === "timeframe" || cmd === "tf") {
      workspace.setTimeframe(arg);
      return;
    }
    if (cmd === "model") {
      const models = useCatalog.getState().models.length ? useCatalog.getState().models : MODELS;
      const hit = models.find((m) => m.id.includes(arg) || m.label.toLowerCase().includes(arg.toLowerCase()));
      if (hit) chat.setModel(hit.id);
      return;
    }
    if (cmd === "overlay" && arg === "clear") {
      workspace.clearOverlays();
      return;
    }
    if (cmd === "scan") {
      const parsed = parsePairShortcut(arg) || workspace.symbol;
      if (parsed !== workspace.symbol) workspace.setSymbol(parsed);
      chat.pushUser(text);
      try {
        const data = await api.structure(parsed, workspace.period.granularity);
        chat.appendAssistant(formatStructure(parsed, workspace.period.text, data));
        const overlays = fvgOverlays(data);
        if (overlays.length) workspace.applyToChart(overlays);
      } catch (err) {
        chat.appendAssistant(err instanceof Error ? err.message : t("chat.scanFailed"));
      }
      return;
    }
    if (cmd === "setup") {
      message = arg || SETUP_PROMPT;
    }
  }

  chat.pushUser(message);
  chat.startRun(`local_${Date.now()}`);
  const controller = new AbortController();
  useChat.setState({ abort: controller });
  try {
    await api.streamChat(
      {
        message,
        symbol: workspace.symbol,
        timeframe: workspace.period.text,
        model: useChat.getState().model,
        sessionId: useSessions.getState().activeId || undefined,
      },
      (event) => {
        const p = event.payload || {};
        const type = event.type;
        if (type === "run_start" && p.runId) useChat.setState({ runId: String(p.runId) });
        if ((type === "agent_thought" || type === "thought" || type === "token") && (p.delta || p.text)) {
          const tok = String(p.delta || p.text);
          useChat.getState().appendThought(String(p.agent || "agent"), tok, p.channel ? String(p.channel) : undefined);
          if (p.channel === "text" || type === "token") useChat.getState().appendToken(tok);
        }
        if (type === "agent_tool_call") {
          useChat.getState().upsertToolCall({
            id: String(p.id || p.name || ""),
            agent: String(p.agent || ""),
            name: String(p.name || ""),
            input: p.input,
          });
        }
        if (type === "agent_tool_result") {
          useChat.getState().upsertToolResult(String(p.id || ""), p.output);
        }
        if (type === "agent_debate_message" && p.text) {
          useChat.getState().addDebate({
            role: String(p.role || ""),
            agent: String(p.agent || p.role || ""),
            text: String(p.text),
          });
        }
        if (type === "agent_memory_recall") {
          useChat.getState().addRecall({
            instrument: p.instrument ? String(p.instrument) : undefined,
            count: typeof p.count === "number" ? p.count : undefined,
            text: p.text ? String(p.text) : undefined,
            lessons: Array.isArray(p.lessons) ? p.lessons.map(String) : undefined,
          });
        }
        if (type === "agent_artifact_start" && p.id) {
          useChat.getState().startArtifact({
            id: String(p.id),
            title: String(p.title || "Artifact"),
            type: String(p.type || "text/markdown"),
            language: p.language ? String(p.language) : undefined,
            agent: p.agent ? String(p.agent) : undefined,
            body: "",
          });
        }
        if (type === "agent_artifact_delta" && p.id && p.text) {
          useChat.getState().appendArtifact(String(p.id), String(p.text));
        }
        if (type === "agent_artifact_end" && p.id) {
          useChat.getState().endArtifact(p as unknown as Artifact);
        }
        if (type === "assistant" && p.text && !p.recommendationId) {
          useChat.getState().appendAssistant(String(p.text));
        }
        if (type === "error" && (p.detail || p.message)) {
          useChat.getState().appendAssistant(String(p.detail || p.message));
        }
        if (type === "run_complete" && p.paused) {
          useChat.getState().appendAssistant(String(p.error || t("settings.paused")));
        }
        if (type === "agent_chart_overlays" && Array.isArray(p.overlays)) {
          useWorkspace.getState().appendToChart(p.overlays as import("@/lib/types").KlineOverlay[]);
        }
        if ((type === "agent_recommendation" || type === "recommendation") && p.id) {
          const rec = p as unknown as TradeRecommendation;
          useRecommendations.getState().upsert(rec);
          useWorkspace.getState().applyToChart(rec.klineOverlays || [], rec.focusTimestamp, rec.id);
          if (rec.rationale) useChat.getState().appendAssistant(rec.rationale, rec.id);
        }
        if (type === "cancelled") {
          useChat.getState().appendAssistant(t("chat.cancelled"));
        }
      },
      controller.signal
    );
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      useChat.getState().appendAssistant(t("chat.cancelled"));
    } else {
      useChat.getState().appendAssistant(err instanceof Error ? err.message : t("chat.agentFailed"));
    }
  } finally {
    useChat.setState({ abort: null });
    useChat.getState().complete();
  }
}
