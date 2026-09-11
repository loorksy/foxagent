"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { createChartOverlay, type ChartLike } from "@/lib/overlays";
import { useT } from "@/i18n";
import type { KlineOverlay, OverlayPoint } from "@/lib/types";

export type PixelChart = ChartLike & {
  convertToPixel?: (
    coords: { timestamp: number; value: number },
    finder: { paneId: string }
  ) => { x?: number; y?: number } | Array<{ x?: number; y?: number }> | null;
};

type CursorPos = { x: number; y: number };

type PendingOverlay = { ov: KlineOverlay; index: number };

type Run = {
  chart: PixelChart;
  pending: PendingOverlay[];
  cancelled: boolean;
  timers: Set<number>;
  resolvers: Set<() => void>;
};

const CURSOR_MOVE_MS = 350;
const BETWEEN_OVERLAYS_MS = 480;
const HIDE_CURSOR_AFTER_MS = 1000;

function prefersReducedMotion(): boolean {
  try {
    return (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  } catch {
    return false;
  }
}

/**
 * Project overlay points to pixel coordinates inside the chart host.
 * Returns null when any point cannot be projected or lands off-screen,
 * signalling the caller to skip animation for that overlay.
 */
function projectPoints(
  chart: PixelChart,
  points: OverlayPoint[],
  host: HTMLElement | null
): CursorPos[] | null {
  if (!chart.convertToPixel || !host || !points.length) return null;
  const width = host.clientWidth;
  const height = host.clientHeight;
  if (width <= 0 || height <= 0) return null;
  const out: CursorPos[] = [];
  for (const p of points) {
    try {
      const raw = chart.convertToPixel(
        { timestamp: p.timestamp, value: p.value },
        { paneId: "candle_pane" }
      );
      const coord = Array.isArray(raw) ? raw[0] : raw;
      if (
        !coord ||
        typeof coord.x !== "number" ||
        typeof coord.y !== "number" ||
        !Number.isFinite(coord.x) ||
        !Number.isFinite(coord.y)
      ) {
        return null;
      }
      if (coord.x < 0 || coord.y < 0 || coord.x > width || coord.y > height) return null;
      out.push({ x: coord.x, y: coord.y });
    } catch {
      return null;
    }
  }
  return out;
}

/**
 * Animates agent-sent overlays onto the chart: a fake cursor travels to each
 * anchor point, the overlay is created when the cursor reaches the last point,
 * and overlays are drawn one after another. Guarantees the final chart state
 * matches the instant path: interrupting (new command, unmount) flushes every
 * pending overlay synchronously with identical ids/groupIds.
 */
export function useAgentDrawing(hostRef: RefObject<HTMLElement | null>) {
  const [cursor, setCursor] = useState<CursorPos | null>(null);
  const [drawing, setDrawing] = useState(false);
  const runRef = useRef<Run | null>(null);

  const interrupt = useCallback(() => {
    const run = runRef.current;
    if (!run) return;
    runRef.current = null;
    run.cancelled = true;
    run.timers.forEach((id) => window.clearTimeout(id));
    run.timers.clear();
    run.resolvers.forEach((resolve) => resolve());
    run.resolvers.clear();
    for (const { ov, index } of run.pending) {
      createChartOverlay(run.chart, ov, index);
    }
    run.pending.length = 0;
    setCursor(null);
    setDrawing(false);
  }, []);

  useEffect(() => interrupt, [interrupt]);

  const draw = useCallback(
    async (chart: PixelChart, overlays: KlineOverlay[], opts?: { initialDelayMs?: number }) => {
      interrupt();
      if (!overlays.length) return;
      if (prefersReducedMotion()) {
        overlays.forEach((ov, i) => createChartOverlay(chart, ov, i));
        return;
      }

      const run: Run = {
        chart,
        pending: overlays.map((ov, index) => ({ ov, index })),
        cancelled: false,
        timers: new Set(),
        resolvers: new Set(),
      };
      runRef.current = run;
      setDrawing(true);

      const sleep = (ms: number) =>
        new Promise<void>((resolve) => {
          if (run.cancelled) {
            resolve();
            return;
          }
          const done = () => {
            run.timers.delete(id);
            run.resolvers.delete(done);
            resolve();
          };
          const id = window.setTimeout(done, ms);
          run.timers.add(id);
          run.resolvers.add(done);
        });

      if (opts?.initialDelayMs) await sleep(opts.initialDelayMs);

      while (run.pending.length && !run.cancelled) {
        const { ov, index } = run.pending[0];
        const pixels = projectPoints(chart, ov.points, hostRef.current);
        if (pixels) {
          for (const pos of pixels) {
            if (run.cancelled) break;
            setCursor(pos);
            await sleep(CURSOR_MOVE_MS + 30);
          }
        }
        if (run.cancelled) break;
        run.pending.shift();
        createChartOverlay(chart, ov, index);
        if (run.pending.length) await sleep(BETWEEN_OVERLAYS_MS);
      }

      if (runRef.current !== run || run.cancelled) return;
      setDrawing(false);
      await sleep(HIDE_CURSOR_AFTER_MS);
      if (runRef.current === run && !run.cancelled) {
        runRef.current = null;
        setCursor(null);
      }
    },
    [hostRef, interrupt]
  );

  return { draw, interrupt, cursor, drawing };
}

/**
 * Overlay layer rendered on top of the chart: the animated cursor glyph and
 * the "FoxAgent is drawing…" status pill. Purely presentational.
 */
export function AgentCursor({ pos, drawing }: { pos: CursorPos | null; drawing: boolean }) {
  const t = useT();
  return (
    <>
      {pos ? (
        <div
          aria-hidden
          className="pointer-events-none absolute left-0 top-0 z-20"
          style={{
            transform: `translate(${pos.x}px, ${pos.y}px)`,
            transition: `transform ${CURSOR_MOVE_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`,
            willChange: "transform",
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            style={{
              transform: "translate(-3px, -2px)",
              filter: "drop-shadow(0 0 4px rgba(232, 200, 114, 0.85))",
            }}
          >
            <path
              d="M3 1.5 L12.5 8.5 L8 9.2 L5.6 13.6 Z"
              fill="#e8c872"
              stroke="#0b0b0f"
              strokeWidth="1"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      ) : null}
      {drawing ? (
        <div className="pointer-events-none absolute start-2 top-2 z-20 flex items-center gap-1 rounded-full border border-amber-400/30 bg-background/80 px-2 py-0.5 text-[11px] text-amber-200 shadow-sm backdrop-blur-sm">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
          {t("chart.agentDrawing")}
        </div>
      ) : null}
    </>
  );
}
