import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useLocale } from "@/i18n";
import { useBotInstances } from "@/stores/botInstances";

vi.mock("@/lib/api", () => ({
  api: {
    botInstances: vi.fn().mockResolvedValue({ instances: [], paused: false }),
    mt5Status: vi.fn().mockResolvedValue({ connected: false }),
    strategies: vi.fn().mockResolvedValue({ strategies: [] }),
  },
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

import BotsRoom from "./page";

const mockBot = {
  id: "bot-test-1",
  name: "Gold Scanner",
  type: "strategy" as const,
  enabled: true,
  scanIntervalSeconds: 60,
  agents: ["multi_strategy"],
  strategyIds: [],
  minRr: 2,
  maxRiskPercent: 1,
  allowedSessions: ["london", "ny", "asian"],
  autoExecute: false,
  orderVolume: 0.01,
  createdAt: "2026-01-01T00:00:00Z",
  stats: { cycles: 12, lastError: "", lastSignalAt: "2026-01-02T10:00:00Z" },
  running: true,
};

describe("Bots room", () => {
  beforeEach(() => {
    useLocale.setState({ locale: "en" });
    useBotInstances.setState({
      instances: [mockBot],
      paused: false,
      loading: false,
      error: "",
      load: vi.fn(),
      create: vi.fn(),
      patch: vi.fn(),
      remove: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    });
  });

  it("shows a bot card and the create button", () => {
    render(<BotsRoom />);
    expect(screen.getByRole("heading", { name: "Bots room" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create bot/i })).toBeInTheDocument();
    expect(screen.getByText("Gold Scanner")).toBeInTheDocument();
    expect(screen.getByText("Strategy bot")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
  });
});
