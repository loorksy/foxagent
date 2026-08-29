"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquare, MessageSquarePlus, Search, Trash2 } from "lucide-react";
import { useSessions } from "@/stores/sessions";
import { cn } from "@/lib/utils";
import { useLocale, useT } from "@/i18n";

function stamp(ts: number, locale: string) {
  try {
    return new Date(ts).toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function Conversations({ collapsed = false }: { collapsed?: boolean }) {
  const sessions = useSessions((s) => s.sessions);
  const activeId = useSessions((s) => s.activeId);
  const query = useSessions((s) => s.query);
  const setQuery = useSessions((s) => s.setQuery);
  const removeChat = useSessions((s) => s.removeChat);
  const router = useRouter();
  const t = useT();
  const locale = useLocale((s) => s.locale);

  const filtered = sessions.filter(
    (s) => !query.trim() || s.title.toLowerCase().includes(query.trim().toLowerCase())
  );

  if (collapsed) {
    return (
      <div className="flex shrink-0 flex-col items-center gap-1 border-t border-sidebar-border py-2">
        <Link
          href="/agents"
          title={t("chats.new")}
          className="flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <MessageSquarePlus className="h-4 w-4" />
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col border-t border-sidebar-border">
      <div className="shrink-0 space-y-2 px-2 py-2">
        <Link
          href="/agents"
          className="flex min-h-9 w-full items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-muted"
        >
          <MessageSquarePlus className="h-4 w-4 shrink-0" />
          {t("chats.new")}
        </Link>
        <label className="relative block">
          <Search className="pointer-events-none absolute start-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("chats.search")}
            className="min-h-9 w-full rounded-lg border border-border bg-background pe-2 ps-8 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <p className="px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("chats.list")}</p>
      </div>
      <div className="fox-scroll min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {filtered.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">{t("chats.empty")}</p>
        ) : (
          filtered.map((s) => (
            <div
              key={s.id}
              className={cn(
                "group mb-0.5 flex items-center gap-1 rounded-lg px-2 py-2",
                activeId === s.id ? "bg-[var(--sidebar-active-bg)]" : "hover:bg-muted"
              )}
            >
              <Link href={`/agents/${s.id}`} className="min-w-0 flex-1 text-start">
                <p className="flex items-center gap-1.5 truncate text-sm text-foreground">
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  {s.title}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground" dir="ltr">
                  {stamp(s.updatedAt, locale)}
                </p>
              </Link>
              <button
                type="button"
                onClick={() => {
                  void removeChat(s.id).then(() => {
                    if (activeId === s.id) router.push("/agents");
                  });
                }}
                className="hidden size-7 items-center justify-center rounded-md text-muted-foreground hover:text-sell group-hover:flex"
                aria-label={t("chats.delete")}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
