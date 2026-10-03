import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useLocale } from "@/i18n";
import { useChat } from "@/stores/chat";
import { activityHeadline, ChatReasoning } from "./ChatReasoning";
import type { RunStep } from "@/lib/types";

const tools: RunStep[] = [
  {
    kind: "tool",
    toolId: "t1",
    toolName: "get_live_price",
    toolLabel: "أقرأ السعر الحي",
    at: 1,
  },
  {
    kind: "tool",
    toolId: "t2",
    toolName: "get_candles",
    toolLabel: "أراجع الشارت",
    toolOutput: { ok: true },
    at: 2,
  },
  {
    kind: "debate",
    role: "bull",
    agent: "BullResearcher",
    text: "should stay in the inspector",
    at: 3,
  },
];

describe("ChatReasoning Hermes-style activity", () => {
  beforeEach(() => {
    useLocale.setState({ locale: "en" });
    useChat.getState().clearChat();
  });

  it("surfaces the running tool as the live headline", () => {
    expect(activityHeadline(tools, true)).toBe("أقرأ السعر الحي");
  });

  it("shows live thinking and tool cards in the transcript, not a hidden dump", () => {
    useChat.setState({
      streaming: true,
      runStartedAt: Date.now() - 2000,
      steps: [
        { kind: "thought", agent: "FoxAgent", text: "checking M15 liquidity", at: Date.now() },
        ...tools,
      ],
    });
    render(<ChatReasoning live />);
    expect(screen.getAllByText("أقرأ السعر الحي").length).toBeGreaterThan(0);
    expect(screen.getAllByText("أراجع الشارت").length).toBeGreaterThan(0);
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText(/checking M15 liquidity/)).toBeInTheDocument();
    expect(screen.queryByText("should stay in the inspector")).not.toBeInTheDocument();
  });

  it("keeps internal debate behind the technical inspector", () => {
    render(<ChatReasoning steps={tools} live={false} />);
    expect(screen.queryByText("should stay in the inspector")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText("should stay in the inspector")).toBeInTheDocument();
  });
});
