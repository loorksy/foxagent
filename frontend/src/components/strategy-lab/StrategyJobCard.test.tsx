import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLocale } from "@/i18n";
import type { StrategyExperimentJob } from "@/lib/types";
import { StrategyJobCard } from "./StrategyJobCard";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const job: StrategyExperimentJob = {
  id: "job_1",
  strategyId: "asian_fvg_fade",
  status: "awaiting_pin",
  maxAttempts: 8,
  passed: true,
  attempts: [
    {
      n: 1,
      change: "initial draft",
      passed: true,
      strategy: {
        id: "asian_fvg_fade",
        name: "Asian FVG fade",
        description: "",
        timeframes: ["M15"],
        direction: "both",
        entry_conditions: {},
        sessions: ["london"],
        stop_rule: "swing",
        tp1_r: 1.5,
        tp2_r: 3,
        max_holding_bars: 24,
        source: "claude_proposed",
        created_by: "claude",
        status: "validated",
      },
      report: { winRate: 0.6, profitFactor: 1.8, maxDrawdownR: 4, totalTrades: 80 },
    },
  ],
  best: undefined,
};

describe("StrategyJobCard", () => {
  it("shows attempt count and waits for a human pin", () => {
    useLocale.setState({ locale: "en" });
    render(<StrategyJobCard job={{ ...job, best: job.attempts[0] }} />);
    expect(screen.getByTestId("strategy-job-card")).toBeInTheDocument();
    expect(screen.getByText(/1\/8/)).toBeInTheDocument();
    expect(screen.getByText("Waiting for pin")).toBeInTheDocument();
    expect(screen.getByText("Pin")).toBeInTheDocument();
  });
});
