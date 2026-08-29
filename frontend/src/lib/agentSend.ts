import { MODELS, parsePairShortcut } from "@/lib/constants";
import { api } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace";
import { useChat } from "@/stores/chat";
import { useRecommendations } from "@/stores/recommendations";
import type { TradeRecommendation } from "@/lib/types";

export async function sendAgentMessage(raw: string) {
  const text = raw.trim();
  const streaming = useChat.getState().streaming;
  if (!text || streaming) return;

  const workspace = useWorkspace.getState();
  const chat = useChat.getState();

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
      const hit = MODELS.find((m) => m.id.includes(arg) || m.label.toLowerCase().includes(arg.toLowerCase()));
      if (hit) chat.setModel(hit.id);
      return;
    }
    if (cmd === "overlay" && arg === "clear") {
      workspace.clearOverlays();
      return;
    }
  }

  chat.pushUser(text);
  chat.startRun(`local_${Date.now()}`);
  try {
    await api.streamChat(
      {
        message: text,
        symbol: workspace.symbol,
        timeframe: workspace.period.text,
        model: useChat.getState().model,
      },
      (event) => {
        const p = event.payload || {};
        if (event.type === "phase" && p.phase) useChat.getState().setPhase(p.phase as never);
        if (event.type === "thought" && p.text) useChat.getState().addThought(String(p.text));
        if (event.type === "token" && p.text) useChat.getState().appendToken(String(p.text));
        if (event.type === "assistant" && p.text && !p.recommendationId) {
          useChat.getState().appendAssistant(String(p.text));
        }
        if (event.type === "recommendation" && p.id) {
          const rec = p as unknown as TradeRecommendation;
          useRecommendations.getState().upsert(rec);
          useWorkspace.getState().applyToChart(rec.klineOverlays || [], rec.focusTimestamp, rec.id);
          if (rec.rationale) useChat.getState().appendAssistant(rec.rationale, rec.id);
        }
      }
    );
  } catch (err) {
    useChat.getState().appendAssistant(err instanceof Error ? err.message : "فشل طلب الوكيل");
  } finally {
    useChat.getState().complete();
  }
}
