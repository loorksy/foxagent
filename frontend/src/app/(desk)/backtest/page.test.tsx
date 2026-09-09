import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BacktestRoute from "./page";
import { useBacktest } from "@/stores/backtest";
import { useStrategyLab } from "@/stores/strategyLab";
import { useLocale } from "@/i18n";

vi.mock("@/lib/api", () => ({
  api: {
    strategies: vi.fn().mockResolvedValue({ strategies: [] }),
    backtestReports: vi.fn().mockResolvedValue({ reports: [] }),
    runBacktest: vi.fn(),
  },
}));

describe("BacktestRoute empty desk", () => {
  beforeEach(() => {
    useLocale.setState({ locale: "en" });
    useBacktest.setState({ report: null, history: [], running: false, error: "" });
    useStrategyLab.setState({ items: [], loading: false, error: "" });
  });

  it("renders without a maximum-update-depth crash when no report is loaded", () => {
    render(<BacktestRoute />);
    expect(screen.getByRole("heading", { name: "Gold backtest" })).toBeInTheDocument();
    expect(screen.getByText("No trades in this window, or the warehouse is empty.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
  });
});
