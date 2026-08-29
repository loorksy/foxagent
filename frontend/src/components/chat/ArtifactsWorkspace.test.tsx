import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ArtifactsWorkspace } from "./ArtifactsWorkspace";
import { useChat } from "@/stores/chat";
import { useLocale } from "@/i18n";

const EMPTY = "No artifacts yet. Reports and blueprints appear here as the crew writes them.";

describe("ArtifactsWorkspace empty deep-link state", () => {
  beforeEach(() => {
    useLocale.setState({ locale: "en" });
    useChat.setState({
      artifacts: [],
      artifactsOpen: true,
      activeArtifactId: null,
    });
  });

  it("renders the empty-state sentence exactly once when opened with no artifacts", () => {
    render(<ArtifactsWorkspace />);
    expect(screen.getAllByText(EMPTY)).toHaveLength(1);
    expect(screen.getByText("Artifacts")).toBeInTheDocument();
  });
});
