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
});
