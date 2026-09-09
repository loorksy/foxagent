import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLocale } from "@/i18n";
import { useInbox } from "@/stores/inbox";

vi.mock("@/lib/api", () => ({
  api: {
    inbox: vi.fn().mockResolvedValue({
      items: [],
      counts: { open: 0, inbox: 0, approvals: 0, alerts: 0 },
      desk: {
        paused: false,
        botRunning: false,
        warehouseStale: false,
        openCount: 0,
        nextEventTitle: null,
        nextEventMinutes: null,
      },
    }),
  },
}));

import InboxRoute from "./page";

describe("Inbox route", () => {
  it("renders the empty Arabic-first desk", () => {
    useLocale.setState({ locale: "en" });
    useInbox.setState({
      items: [],
      tab: "inbox",
      desk: {
        paused: false,
        botRunning: false,
        warehouseStale: false,
        openCount: 0,
      },
      counts: { open: 0, inbox: 0, approvals: 0, alerts: 0 },
      loading: false,
      error: "",
    });
    render(<InboxRoute />);
    expect(screen.getByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    expect(screen.getByText(/Nothing waiting/)).toBeInTheDocument();
  });
});
