import { describe, expect, it, beforeEach } from "vitest";
import { useChat } from "./chat";

describe("chat tool timeline", () => {
  beforeEach(() => {
    useChat.getState().clearChat();
  });

  it("marks a tool done when the result arrives by name", () => {
    useChat.getState().startRun("run_1");
    useChat.getState().upsertToolCall({ id: "abc", agent: "FoxAgent", name: "get_candles", label: "أراجع الشارت" });
    useChat.getState().upsertToolResult("", { count: 2 }, "get_candles");
    const step = useChat.getState().steps.find((s) => s.kind === "tool");
    expect(step?.toolLabel).toBe("أراجع الشارت");
    expect(step?.toolOutput).toEqual({ count: 2 });
  });

  it("clears leftover spinners when the run completes", () => {
    useChat.getState().startRun("run_2");
    useChat.getState().upsertToolCall({ id: "x", agent: "FoxAgent", name: "structure_scan", label: "أراجع النماذج" });
    useChat.getState().complete();
    const step = useChat.getState().steps.find((s) => s.kind === "tool");
    expect(step?.toolOutput).toEqual({ ok: true });
  });

  it("pins the activity timeline onto the finished assistant message", () => {
    useChat.getState().startRun("run_3");
    useChat.getState().upsertToolCall({ id: "p", agent: "FoxAgent", name: "get_live_price", label: "أقرأ السعر الحي" });
    useChat.getState().complete();
    const assistant = useChat.getState().messages.find((m) => m.role === "assistant");
    expect(assistant?.streaming).toBe(false);
    expect(assistant?.steps?.some((s) => s.toolLabel === "أقرأ السعر الحي")).toBe(true);
  });

  it("queues the next operator message while a run is live", () => {
    useChat.getState().startRun("run_4");
    useChat.getState().queueMessage("حلل لندن");
    expect(useChat.getState().queuedText).toBe("حلل لندن");
    useChat.getState().clearQueue();
    expect(useChat.getState().queuedText).toBeNull();
  });
});
