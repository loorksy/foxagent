"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { useWorkspace } from "@/stores/workspace";
import { api } from "@/lib/api";
import { DARK_CHART_STYLES } from "@/lib/chart-styles";
import { applyOverlays, clearOverlays, focusTimestamp, type ChartLike } from "@/lib/overlays";
import { cn } from "@/lib/utils";
import type { KLineBar, KlineOverlay } from "@/lib/types";

export type ChartHandle = {
  apply: (overlays: KlineOverlay[], ts?: number | null) => Promise<void>;
  clear: () => void;
  focus: (ts: number) => void;
};

type ChartApi = ChartLike & {
  applyNewData: (bars: KLineBar[]) => void;
  updateData: (bar: KLineBar) => void;
  createIndicator: (name: string, isStack?: boolean, pane?: { id: string }) => void;
  resize: () => void;
};

type Props = {
  className?: string;
};

const ChartCanvas = forwardRef<ChartHandle, Props>(function ChartCanvas({ className }, ref) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ChartApi | null>(null);
  const barsRef = useRef<KLineBar[]>([]);
  const symbol = useWorkspace((s) => s.symbol);
  const period = useWorkspace((s) => s.period);
  const chartNonce = useWorkspace((s) => s.chartNonce);
  const command = useWorkspace((s) => s.command);
  const prices = useWorkspace((s) => s.prices);

  useImperativeHandle(ref, () => ({
    apply: async (overlays, ts) => {
      if (!chartRef.current) return;
      clearOverlays(chartRef.current);
      await applyOverlays(chartRef.current, overlays, true);
      focusTimestamp(chartRef.current, ts);
    },
    clear: () => chartRef.current && clearOverlays(chartRef.current),
    focus: (ts) => chartRef.current && focusTimestamp(chartRef.current, ts),
  }));

  useEffect(() => {
    let disposed = false;
    let ro: ResizeObserver | null = null;

    async function boot() {
      const mod = await import("klinecharts");
      if (disposed || !hostRef.current) return;
      if (chartRef.current) {
        mod.dispose(hostRef.current);
        chartRef.current = null;
      }
      const chart = mod.init(hostRef.current, {
        styles: DARK_CHART_STYLES,
      } as Parameters<typeof mod.init>[1]) as ChartApi | null;
      if (!chart) return;
      chartRef.current = chart;
      try {
        chart.createIndicator("MA", false, { id: "candle_pane" });
        chart.createIndicator("VOL");
        chart.createIndicator("MACD");
      } catch {
        /* indicators optional */
      }
      ro = new ResizeObserver(() => {
        try {
          chart.resize();
        } catch {
          /* ignore */
        }
      });
      ro.observe(hostRef.current);
      await loadHistory(chart);
    }

    async function loadHistory(chart: ChartApi) {
      try {
        const data = await api.candles(symbol, period.granularity, 400);
        barsRef.current = data.candles;
        chart.applyNewData(data.candles);
      } catch (err) {
        console.error(err);
      }
    }

    const host = hostRef.current;
    boot();
    return () => {
      disposed = true;
      ro?.disconnect();
      if (host) {
        import("klinecharts").then((mod) => {
          try {
            mod.dispose(host);
          } catch {
            /* ignore */
          }
        });
      }
      chartRef.current = null;
    };
  }, [symbol, period.granularity, chartNonce]);

  useEffect(() => {
    const chart = chartRef.current;
    const tick = prices[symbol];
    if (!chart || !tick || !barsRef.current.length) return;
    const last = { ...barsRef.current[barsRef.current.length - 1] };
    last.close = tick.mid;
    last.high = Math.max(last.high, tick.mid);
    last.low = Math.min(last.low, tick.mid);
    last.timestamp = last.timestamp;
    barsRef.current[barsRef.current.length - 1] = last;
    try {
      chart.updateData(last);
    } catch {
      /* ignore */
    }
  }, [prices, symbol]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !command) return;
    if (command.type === "clear") {
      clearOverlays(chart);
    } else if (command.type === "focus") {
      focusTimestamp(chart, command.timestamp);
    } else if (command.type === "apply") {
      clearOverlays(chart);
      applyOverlays(chart, command.overlays, true).then(() => {
        focusTimestamp(chart, command.focusTimestamp);
      });
    }
  }, [command]);

  return (
    <div className={cn("h-full w-full bg-background", className)}>
      <div ref={hostRef} className="h-full w-full" />
    </div>
  );
});

export default ChartCanvas;
