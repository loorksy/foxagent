import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLocale } from "@/i18n";
import type { InboxItem } from "@/lib/types";
import { InboxList } from "./InboxList";

const emptyApprove = async () => undefined;

describe("InboxList", () => {
  it("shows an explicit empty desk, not a blank crash", () => {
    useLocale.setState({ locale: "en" });
    render(
      <InboxList
        items={[]}
        tab="inbox"
        onTab={() => undefined}
        empty="Nothing waiting. Warehouse is fresh and no signals need you."
        onApprove={emptyApprove}
        onReject={emptyApprove}
        onAck={emptyApprove}
      />
    );
    expect(screen.getByText(/Nothing waiting/)).toBeInTheDocument();
    expect(screen.getByText("Inbox")).toBeInTheDocument();
    expect(screen.getByText("Approvals")).toBeInTheDocument();
  });

  it("renders an approval card with entry, stop, and R", () => {
    useLocale.setState({ locale: "en" });
    const item: InboxItem = {
      id: "signal:sig_1",
      tab: "approvals",
      kind: "signal",
      title: "gold_liquidity_sniper · BUY",
      summary: "XAU_USD M15",
      severity: "high",
      href: "/inbox/signal:sig_1",
      sourceHref: "/bot",
      payload: {
        signal: {
          id: "sig_1",
          agentType: "multi_strategy",
          strategyId: "gold_liquidity_sniper",
          instrument: "XAU_USD",
          timeframe: "M15",
          signalType: "buy",
          entryPrice: 2650,
          stopLoss: 2644,
          takeProfit1: 2659,
          takeProfit2: 2668,
          confidence: 0.86,
          riskReward: 3,
          status: "pending",
        },
      },
    };
    render(
      <InboxList
        items={[item]}
        tab="approvals"
        onTab={() => undefined}
        empty="none"
        onApprove={emptyApprove}
        onReject={emptyApprove}
        onAck={emptyApprove}
      />
    );
    expect(screen.getByText(/gold_liquidity_sniper/)).toBeInTheDocument();
    expect(screen.getByText("Approve")).toBeInTheDocument();
    expect(screen.getByText("Reject")).toBeInTheDocument();
    expect(screen.getByText("2650")).toBeInTheDocument();
  });
});
