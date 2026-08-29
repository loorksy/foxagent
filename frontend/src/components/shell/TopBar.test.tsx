import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "./TopBar";
import { useChat } from "@/stores/chat";
import { useLocale } from "@/i18n";
import type { Artifact } from "@/lib/types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/agents",
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const SAMPLE: Artifact = {
  id: "art_1",
  title: "Risk matrix",
  type: "text/csv",
  body: "Setup,R\nXAU,1.6",
};

describe("TopBar artifacts trigger", () => {
  beforeEach(() => {
    useLocale.setState({ locale: "en" });
    useChat.setState({
      artifacts: [],
      artifactsOpen: false,
      messages: [{ id: "m1", role: "user", text: "scan", createdAt: 1 }],
    });
  });

  it("hides the Artifacts button when there are no artifacts", () => {
    render(<TopBar />);
    expect(screen.queryByRole("button", { name: "Artifacts" })).not.toBeInTheDocument();
  });

  it("shows the Artifacts button when at least one artifact exists", () => {
    useChat.setState({ artifacts: [SAMPLE] });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: "Artifacts" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Artifacts" })).toBeEnabled();
  });
});
