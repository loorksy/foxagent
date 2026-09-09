import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLocale } from "@/i18n";
import { useInbox } from "@/stores/inbox";

vi.mock("@/lib/api", () => ({
  api: {
    botsRoom: vi.fn().mockResolvedValue({
      agents: [],
      news: { open: false },
      circuits: { safeMode: false },
      running: { running: false },
    }),
    botStatus: vi.fn().mockResolvedValue({ running: false, cycles: 0, lastError: "" }),
    botSignals: vi.fn().mockResolvedValue({ signals: [] }),
    botPerformance: vi.fn().mockResolvedValue({ performance: [] }),
    botPreflight: vi.fn().mockResolvedValue({ ok: true, checks: [] }),
    economicCalendar: vi.fn().mockResolvedValue({ events: [], source: "" }),
    strategies: vi.fn().mockResolvedValue({ strategies: [] }),
    settings: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

import BotsRoom from "./page";

describe("Bots room", () => {
  it("shows an explicit stopped desk, not a blank crash", () => {
    useLocale.setState({ locale: "en" });
    useInbox.setState({
      desk: { paused: false, botRunning: false, warehouseStale: false, openCount: 0 },
    } as never);
    render(<BotsRoom />);
    expect(screen.getByRole("heading", { name: "Bots room" })).toBeInTheDocument();
    expect(screen.getAllByText("Off or silent").length).toBeGreaterThan(0);
  });
});
