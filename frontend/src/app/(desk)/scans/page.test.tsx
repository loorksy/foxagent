import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLocale } from "@/i18n";

vi.mock("@/lib/api", () => ({
  api: {
    botScans: vi.fn().mockResolvedValue({ scans: [] }),
  },
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

import ScansPage from "./page";

describe("Scans journal", () => {
  it("shows an explicit empty timeline", () => {
    useLocale.setState({ locale: "en" });
    render(<ScansPage />);
    expect(screen.getByRole("heading", { name: "Scan journal" })).toBeInTheDocument();
    expect(screen.getByText(/No cycles recorded yet/)).toBeInTheDocument();
  });
});
