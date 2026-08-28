"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { HeaderBar } from "./HeaderBar";
import { AgentConsole } from "./AgentConsole";
import { RecommendationsLedger } from "./RecommendationsLedger";
import { SettingsDrawer } from "./SettingsDrawer";
import { api, wsUrl } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace";
import { useRecommendations } from "@/stores/recommendations";
import { useSettings } from "@/stores/settings";
import { cn } from "@/lib/utils";
import type { LivePrice } from "@/lib/types";

const ChartCanvas = dynamic(() => import("./ChartCanvas"), { ssr: false });

export function Workstation() {
  const viewMode = useWorkspace((s) => s.viewMode);
  const setPrice = useWorkspace((s) => s.setPrice);
  const setDataMode = useWorkspace((s) => s.setDataMode);
  const hydrate = useRecommendations((s) => s.hydrate);
  const markFromPrice = useRecommendations((s) => s.markFromPrice);
  const loadSettings = useSettings((s) => s.load);

  useEffect(() => {
    void hydrate();
    void loadSettings()
      .then(() => {
        const pub = useSettings.getState().public;
        if (pub?.dataMode) setDataMode(pub.dataMode);
      })
      .catch(() => undefined);
    void api
      .health()
      .then((h) => setDataMode(h.dataMode as "oanda" | "simulator"))
      .catch(() => undefined);
  }, [hydrate, loadSettings, setDataMode]);

  useEffect(() => {
    let stop = false;
    async function poll() {
      while (!stop) {
        try {
          const data = await api.prices();
          data.prices.forEach((px) => {
            setPrice(px);
            markFromPrice(px.instrument, px.mid);
          });
        } catch {
          /* ignore */
        }
        await new Promise((r) => setTimeout(r, 900));
      }
    }
    void poll();
    return () => {
      stop = true;
    };
  }, [markFromPrice, setPrice]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(wsUrl("/ws/market"));
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "tick") {
            const px = msg.payload as LivePrice;
            setPrice(px);
            markFromPrice(px.instrument, px.mid);
          }
        } catch {
          /* ignore */
        }
      };
    } catch {
      /* polling fallback */
    }
    return () => {
      ws?.close();
    };
  }, [markFromPrice, setPrice]);

  return (
    <div className="flex h-screen min-h-0 flex-col gap-3 p-3">
      <HeaderBar />
      <div
        className={cn(
          "grid min-h-0 flex-1 gap-3",
          viewMode === "split" && "grid-cols-1 xl:grid-cols-[minmax(0,1.65fr)_minmax(360px,0.95fr)]",
          viewMode === "chart" && "grid-cols-1",
          viewMode === "chat" && "grid-cols-1"
        )}
      >
        {viewMode !== "chat" && (
          <div className="glass relative min-h-[320px] overflow-hidden rounded-2xl">
            <ChartCanvas className="absolute inset-0" />
            <div className="pointer-events-none absolute left-4 top-3 text-[10px] uppercase tracking-[0.2em] text-slate-500">
              klinecharts-pro engine · OANDA / simulator feed
            </div>
          </div>
        )}
        {viewMode !== "chart" && (
          <div
            className={cn(
              "grid min-h-0 gap-3",
              viewMode === "chat"
                ? "grid-cols-1 lg:grid-cols-2"
                : "grid-rows-[minmax(0,1.15fr)_minmax(220px,0.85fr)]"
            )}
          >
            <AgentConsole />
            <RecommendationsLedger />
          </div>
        )}
      </div>
      <SettingsDrawer />
    </div>
  );
}
