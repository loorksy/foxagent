"use client";

import { CandlestickChart, FileStack, PanelLeft, RefreshCw, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useUi } from "@/stores/ui";
import { useWorkspace } from "@/stores/workspace";
import { useChat } from "@/stores/chat";
import { displaySymbol } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

const ICON =
  "flex size-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground";

export function TopBar() {
  const mobileOpen = useUi((s) => s.mobileOpen);
  const setMobileOpen = useUi((s) => s.setMobileOpen);
  const pathname = usePathname() || "/";
  const section = pathname.startsWith("/settings") ? "settings" : pathname.startsWith("/recommendations") ? "recommendations" : "chat";
  const artifactsOpen = useChat((s) => s.artifactsOpen);
  const setArtifactsOpen = useChat((s) => s.setArtifactsOpen);
  const toggleChart = useWorkspace((s) => s.toggleChart);
  const chartOpen = useWorkspace((s) => s.chartOpen);
  const symbol = useWorkspace((s) => s.symbol);
  const period = useWorkspace((s) => s.period);
  const dataMode = useWorkspace((s) => s.dataMode);
  const prices = useWorkspace((s) => s.prices);
  const messages = useChat((s) => s.messages);
  const [spinning, setSpinning] = useState(false);
  const tick = prices[symbol];
  const t = useT();

  return (
    <div className="flex h-14 shrink-0 items-center gap-1 border-b border-border px-2 sm:px-3">
      <button
        type="button"
        onClick={() => setMobileOpen(!mobileOpen)}
        className={cn(ICON, "lg:hidden")}
        aria-label={t("topbar.menu")}
      >
        <PanelLeft className="h-5 w-5 rtl:-scale-x-100" />
      </button>
      <div className="ms-auto flex min-w-0 flex-1 items-center justify-end gap-1 overflow-x-auto [scrollbar-width:none]">
        <span className="hidden rounded-full border border-border px-2.5 py-1 font-mono text-[11px] text-muted-foreground sm:inline" dir="ltr">
          {displaySymbol(symbol)} · {period.text}
        </span>
        {tick ? (
          <span className="rounded-full border border-border px-2.5 py-1 font-mono text-[11px] tabular-nums" dir="ltr">
            {tick.mid}
          </span>
        ) : null}
        <span className="rounded-full border border-border px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
          {dataMode === "oanda" ? t("topbar.live") : t("topbar.simulator")}
        </span>
        {section === "chat" && messages.length > 0 && (
          <button
            type="button"
            onClick={toggleChart}
            className={cn(ICON, chartOpen && "bg-muted text-foreground")}
            aria-label={t("topbar.chart")}
            title={t("topbar.showChart")}
          >
            <CandlestickChart className="h-5 w-5" />
          </button>
        )}
        {section === "chat" && (
          <button
            type="button"
            onClick={() => setArtifactsOpen(!artifactsOpen)}
            className={cn(ICON, artifactsOpen && "bg-muted text-foreground")}
            aria-label={t("artifacts.open")}
            title={t("artifacts.title")}
          >
            <FileStack className="h-5 w-5" />
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setSpinning(true);
            window.setTimeout(() => setSpinning(false), 600);
            useWorkspace.setState({ chartNonce: Date.now() });
          }}
          className={ICON}
          aria-label={t("topbar.refresh")}
        >
          <RefreshCw className={cn("h-5 w-5", spinning && "animate-spin")} />
        </button>
        <Link href="/settings" className={ICON} aria-label={t("topbar.settings")}>
          <Settings className="h-5 w-5" />
        </Link>
      </div>
    </div>
  );
}
