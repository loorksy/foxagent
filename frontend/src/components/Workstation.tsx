"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { Sidebar } from "./shell/Sidebar";
import { TopBar } from "./shell/TopBar";
import { ChatPanel } from "./chat/ChatPanel";
import { RecommendationsPage } from "./recs/RecommendationsPage";
import { SettingsPanel } from "./settings/SettingsPanel";
import { api, wsUrl } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace";
import { useRecommendations } from "@/stores/recommendations";
import { useSettings } from "@/stores/settings";
import { useSessions } from "@/stores/sessions";
import { useUi } from "@/stores/ui";
import { cn } from "@/lib/utils";
import type { LivePrice } from "@/lib/types";

const ChartCanvas = dynamic(() => import("./ChartCanvas"), { ssr: false });

export function Workstation() {
  const section = useUi((s) => s.section);
  const chartOpen = useWorkspace((s) => s.chartOpen);
  const setChartOpen = useWorkspace((s) => s.setChartOpen);
  const setPrice = useWorkspace((s) => s.setPrice);
  const setDataMode = useWorkspace((s) => s.setDataMode);
  const hydrate = useRecommendations((s) => s.hydrate);
  const markFromPrice = useRecommendations((s) => s.markFromPrice);
  const loadSettings = useSettings((s) => s.load);
  const hydrateSessions = useSessions((s) => s.hydrate);

  useEffect(() => {
    hydrateSessions();
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
  }, [hydrate, hydrateSessions, loadSettings, setDataMode]);

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
    <div className="relative flex h-dvh overflow-hidden bg-background lg:flex-row" dir="rtl">
      <Sidebar />
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
        <TopBar />
        <main className="aichart-scroll flex min-h-0 flex-1 flex-col overflow-hidden">
          {section === "chat" && (
            <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
              <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                <ChatPanel />
              </div>
              {chartOpen && (
                <div className="hidden min-h-0 w-[min(52%,40rem)] shrink-0 border-s border-border xl:block">
                  <ChartCanvas className="h-full w-full" />
                </div>
              )}
              {chartOpen && (
                <div className="xl:hidden">
                  <button type="button" className="absolute inset-0 z-30 bg-black/50" aria-label="إغلاق الشارت" onClick={() => setChartOpen(false)} />
                  <div className="absolute inset-x-0 bottom-0 z-40 h-[72dvh] overflow-hidden rounded-t-2xl border-t border-border bg-background shadow-xl">
                    <div className="flex h-10 items-center justify-center">
                      <span className="h-1 w-10 rounded-full bg-muted-foreground/40" />
                    </div>
                    <ChartCanvas className="h-[calc(72dvh-2.5rem)] w-full" />
                  </div>
                </div>
              )}
            </div>
          )}
          {section === "recommendations" && <RecommendationsPage />}
          {section === "settings" && <SettingsPanel />}
        </main>
      </div>
    </div>
  );
}
