import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLocale } from "@/i18n";
import { PostMortemForm } from "./PostMortemForm";

vi.mock("@/lib/api", () => ({
  api: {
    postmortem: vi.fn().mockResolvedValue({ ok: true }),
  },
}));

describe("PostMortemForm", () => {
  it("renders thesis, invalidation, and lesson fields", () => {
    useLocale.setState({ locale: "en" });
    render(<PostMortemForm recId="rec_1" defaultThesis="Asia sweep into FVG" />);
    expect(screen.getByTestId("postmortem-form")).toBeInTheDocument();
    expect(screen.getByText("Thesis")).toBeInTheDocument();
    expect(screen.getByText("Invalidation")).toBeInTheDocument();
    expect(screen.getByText("Lesson")).toBeInTheDocument();
    expect(screen.getByText("Save post-mortem")).toBeInTheDocument();
  });
});
