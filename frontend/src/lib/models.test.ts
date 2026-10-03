import { describe, expect, it } from "vitest";
import { MODELS } from "./constants";

describe("model catalog", () => {
  it("lets the operator choose Z.ai beside Claude", () => {
    expect(MODELS[0]?.id).toBe("claude-sonnet-4-5");
    expect(MODELS.some((model) => model.provider === "anthropic")).toBe(true);
    expect(MODELS.find((model) => model.id === "glm-5.3")?.provider).toBe("zai");
  });
});
