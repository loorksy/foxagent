import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLocale } from "@/i18n";
import { ChatUsageMeter, formatUsage } from "./ChatUsageMeter";

describe("ChatUsageMeter", () => {
  it("formats a run the way chat platforms show consumption", () => {
    expect(formatUsage({ inputTokens: 2100, outputTokens: 840, totalTokens: 2940, estimatedUsd: 0.019 })).toContain("2.1k↓");
    expect(formatUsage({ inputTokens: 2100, outputTokens: 840, totalTokens: 2940, estimatedUsd: 0.019 })).toContain("840↑");
  });

  it("renders nothing when the run has not consumed tokens yet", () => {
    useLocale.setState({ locale: "en" });
    const { container } = render(<ChatUsageMeter usage={{ inputTokens: 0, outputTokens: 0, totalTokens: 0 }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a live usage line for the current run", () => {
    useLocale.setState({ locale: "en" });
    render(
      <ChatUsageMeter
        live
        usage={{ inputTokens: 1200, outputTokens: 300, totalTokens: 1500, estimatedUsd: 0.008, calls: 3 }}
      />
    );
    expect(screen.getByText(/Usage/)).toBeInTheDocument();
    expect(screen.getByText(/1.2k↓/)).toBeInTheDocument();
    expect(screen.getByText(/3×/)).toBeInTheDocument();
  });
});
