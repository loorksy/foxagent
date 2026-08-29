"use client";

import { LineChart, MessageSquareText, PanelLeft, PanelLeftClose, Settings, X } from "lucide-react";
import { FoxLogo } from "./FoxLogo";
import { Conversations } from "./Conversations";
import { useUi, type UiSection } from "@/stores/ui";
import { cn } from "@/lib/utils";

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1";

const NAV: { id: UiSection; label: string; icon: typeof MessageSquareText }[] = [
  { id: "chat", label: "المحادثة", icon: MessageSquareText },
  { id: "recommendations", label: "التوصيات", icon: LineChart },
  { id: "settings", label: "الإعدادات", icon: Settings },
];

function NavList({ iconOnly, onNavigate }: { iconOnly: boolean; onNavigate?: () => void }) {
  const section = useUi((s) => s.section);
  const setSection = useUi((s) => s.setSection);
  return (
    <nav className="flex shrink-0 flex-col gap-0.5 px-2 py-2" aria-label="التنقل">
      {NAV.map((item) => {
        const Icon = item.icon;
        const active = section === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              setSection(item.id);
              onNavigate?.();
            }}
            title={iconOnly ? item.label : undefined}
            className={cn(
              "relative flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors lg:min-h-10",
              FOCUS,
              iconOnly && "justify-center px-0",
              active ? "bg-[var(--sidebar-active-bg)] text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {active && <span className="absolute inset-y-2 start-0 w-0.5 rounded-full bg-foreground" />}
            <Icon className={cn("shrink-0", iconOnly ? "h-5 w-5" : "h-4 w-4")} />
            {!iconOnly && <span className="truncate">{item.label}</span>}
          </button>
        );
      })}
    </nav>
  );
}

export function Sidebar() {
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const setCollapsed = useUi((s) => s.setSidebarCollapsed);
  const mobileOpen = useUi((s) => s.mobileOpen);
  const setMobileOpen = useUi((s) => s.setMobileOpen);

  const header = (
    <div className={cn("flex h-14 shrink-0 items-center border-b border-sidebar-border px-3", collapsed ? "justify-center" : "justify-between gap-2")}>
      {!collapsed ? (
        <>
          <button type="button" onClick={() => useUi.getState().setSection("chat")} className={cn("flex min-w-0 items-center rounded-lg", FOCUS)}>
            <FoxLogo size={36} showName nameClassName="truncate text-[15px] font-semibold tracking-tight" />
          </button>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className={cn("hidden size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground lg:flex", FOCUS)}
            aria-label="طي الشريط"
          >
            <PanelLeftClose className="h-4 w-4 rtl:-scale-x-100" />
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className={cn("group relative hidden size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted lg:flex", FOCUS)}
          aria-label="توسيع الشريط"
        >
          <span className="opacity-100 group-hover:opacity-0">
            <FoxLogo size={30} />
          </span>
          <PanelLeft className="absolute h-4 w-4 opacity-0 group-hover:opacity-100 rtl:-scale-x-100" />
        </button>
      )}
    </div>
  );

  return (
    <>
      <aside
        className={cn(
          "z-20 hidden h-full shrink-0 flex-col border-e border-sidebar-border bg-sidebar text-foreground transition-[width] duration-200 lg:flex",
          collapsed ? "w-[3.75rem]" : "w-[260px]"
        )}
      >
        {header}
        <NavList iconOnly={collapsed} />
        <Conversations collapsed={collapsed} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" className="absolute inset-0 bg-black/60" aria-label="إغلاق" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 start-0 flex w-[min(86%,17.5rem)] flex-col border-e border-sidebar-border bg-sidebar shadow-xl">
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-sidebar-border px-3">
              <FoxLogo size={32} showName nameClassName="truncate text-[15px] font-semibold" />
              <button type="button" onClick={() => setMobileOpen(false)} className="flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted">
                <X className="h-5 w-5" />
              </button>
            </div>
            <NavList iconOnly={false} onNavigate={() => setMobileOpen(false)} />
            <Conversations />
          </aside>
        </div>
      )}
    </>
  );
}
