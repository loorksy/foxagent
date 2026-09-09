import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLocale } from "@/i18n";
import { useBacktest } from "@/stores/backtest";
import { BacktestHistory } from "./BacktestHistory";

describe("BacktestHistory", () => {
  it("renders an empty history without crashing", () => {
    useLocale.setState({ locale: "en" });
    useBacktest.setState({ history: [], report: null, running: false, error: "" });
    render(<BacktestHistory />);
    expect(screen.getByText("No saved reports yet.")).toBeInTheDocument();
  });
});
