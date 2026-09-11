import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BacktestRoute from "./page";
import { useBacktest } from "@/stores/backtest";
import { useStrategyLab } from "@/stores/strategyLab";
import { useLocale } from "@/i18n";
import type { BacktestReport, BacktestTrade } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  api: {
    strategies: vi.fn().mockResolvedValue({ strategies: [] }),
    backtestReports: vi.fn().mockResolvedValue({ reports: [] }),
    runBacktest: vi.fn(),
  },
}));

const trade = (pnlR: number, i: number): BacktestTrade => ({
  strategyId: "gold_breakout",
  timeframe: "M15",
  entryTime: `2025-03-0${i + 1}T10:00:00`,
  exitTime: `2025-03-0${i + 1}T14:00:00`,
  direction: i % 2 ? "sell" : "buy",
  entryPrice: 2300 + i,
  stopLoss: 2290,
  takeProfit1: 2310,
  takeProfit2: 2320,
  exitPrice: 2305 + i,
  pnlR,
  pnlPercent: pnlR,
  exitReason: "tp1",
});

const report: BacktestReport = {
  id: "r1",
  symbol: "XAUUSD",
  timeframe: "M15",
  strategyId: "gold_breakout",
  days: 365,
  candlesTested: 12000,
  totalTrades: 3,
  wins: 2,
  losses: 1,
  winRate: 0.667,
  averageR: 0.5,
  totalR: 1.5,
  profitFactor: 2.1,
  maxDrawdownR: 1.0,
  trades: [trade(1.5, 0), trade(-1, 1), trade(1, 2)],
  byStrategy: { gold_breakout: { trades: 3, wins: 2, losses: 1, winRate: 0.667, totalR: 1.5 } },
  bySession: { london: { trades: 3, wins: 2, losses: 1, winRate: 0.667, totalR: 1.5 } },
  byMonth: { "2025-03": { trades: 3, wins: 2, losses: 1, winRate: 0.667, totalR: 1.5 } },
  textReport: "sample",
};

describe("BacktestRoute with a loaded report", () => {
  beforeEach(() => {
    useLocale.setState({ locale: "ar" });
    useBacktest.setState({ report, history: [report], running: false, error: "" });
    useStrategyLab.setState({ items: [], loading: false, error: "" });
  });

  it("renders hero metrics, equity curve and trades without crashing", () => {
    render(<BacktestRoute />);
    expect(screen.getByText("صافي R")).toBeInTheDocument();
    expect(screen.getAllByText("+1.50R").length).toBeGreaterThan(0);
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "منحنى R التراكمي" })).toBeInTheDocument();
    expect(screen.getAllByText("كسر النطاق").length).toBeGreaterThan(0);
  });
});
