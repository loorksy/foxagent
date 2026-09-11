import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLocale } from "@/i18n";
import type { KlineOverlay } from "@/lib/types";
import { AgentCursor, useAgentDrawing, type PixelChart } from "./AgentCursor";

type FakeChart = PixelChart & { created: string[] };

function makeChart(opts?: { offscreen?: boolean }): FakeChart {
  const chart: FakeChart = {
    created: [],
    createOverlay: (o) => {
      chart.created.push(String(o.id));
      return String(o.id);
    },
    removeOverlay: () => undefined,
    convertToPixel: (coords) =>
      opts?.offscreen ? { x: -50, y: 10 } : { x: coords.value, y: coords.value },
  };
  return chart;
}

function makeHost(): HTMLDivElement {
  const host = document.createElement("div");
  Object.defineProperty(host, "clientWidth", { value: 800 });
  Object.defineProperty(host, "clientHeight", { value: 600 });
  return host;
}

const overlays: KlineOverlay[] = [
  {
    name: "trendLine",
    id: "line-a",
    points: [
      { timestamp: 1, value: 100 },
      { timestamp: 2, value: 200 },
    ],
  },
  {
    name: "priceLine",
    id: "price-b",
    points: [{ timestamp: 3, value: 300 }],
  },
];

describe("useAgentDrawing", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("creates every overlay in order once the animation completes", async () => {
    const chart = makeChart();
    const hostRef = { current: makeHost() };
    const { result } = renderHook(() => useAgentDrawing(hostRef));

    let done!: Promise<void>;
    act(() => {
      done = result.current.draw(chart, overlays);
    });
    expect(result.current.drawing).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
      await done;
    });

    expect(chart.created).toEqual(["line-a", "price-b"]);
    expect(result.current.drawing).toBe(false);
    expect(result.current.cursor).toBeNull();
  });

  it("flushes pending overlays instantly when interrupted mid-animation", async () => {
    const chart = makeChart();
    const hostRef = { current: makeHost() };
    const { result } = renderHook(() => useAgentDrawing(hostRef));

    let done!: Promise<void>;
    act(() => {
      done = result.current.draw(chart, overlays);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(chart.created).toEqual([]);

    await act(async () => {
      result.current.interrupt();
      await done;
    });

    expect(chart.created).toEqual(["line-a", "price-b"]);
    expect(result.current.drawing).toBe(false);
    expect(result.current.cursor).toBeNull();
  });

  it("adds overlays instantly when points are off-screen", async () => {
    const chart = makeChart({ offscreen: true });
    const hostRef = { current: makeHost() };
    const { result } = renderHook(() => useAgentDrawing(hostRef));

    let done!: Promise<void>;
    act(() => {
      done = result.current.draw(chart, overlays);
    });
    // First overlay is created synchronously (no cursor travel).
    expect(chart.created).toEqual(["line-a"]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
      await done;
    });
    expect(chart.created).toEqual(["line-a", "price-b"]);
  });

  it("adds all overlays instantly under prefers-reduced-motion", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })
    );
    const chart = makeChart();
    const hostRef = { current: makeHost() };
    const { result } = renderHook(() => useAgentDrawing(hostRef));

    await act(async () => {
      await result.current.draw(chart, overlays);
    });

    expect(chart.created).toEqual(["line-a", "price-b"]);
    expect(result.current.drawing).toBe(false);
    expect(result.current.cursor).toBeNull();
  });
});

describe("AgentCursor", () => {
  it("shows the drawing status pill and cursor glyph", () => {
    useLocale.setState({ locale: "en" });
    const { container } = render(<AgentCursor pos={{ x: 10, y: 20 }} drawing />);
    expect(screen.getByText(/FoxAgent is drawing/)).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
