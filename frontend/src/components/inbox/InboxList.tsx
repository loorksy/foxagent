"use client";

import type { InboxItem, InboxTab } from "@/lib/types";
import { useT, type MessageKey } from "@/i18n";
import { InboxItemRow } from "./InboxItem";

const TABS: { key: InboxTab; label: MessageKey }[] = [
  { key: "inbox", label: "inbox.tab.inbox" },
  { key: "approvals", label: "inbox.tab.approvals" },
  { key: "alerts", label: "inbox.tab.alerts" },
];

export function InboxList({
  items,
  tab,
  onTab,
  empty,
  onApprove,
  onReject,
  onAck,
}: {
  items: InboxItem[];
  tab: InboxTab;
  onTab: (tab: InboxTab) => void;
  empty: string;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string, reason: string) => Promise<void>;
  onAck: (id: string) => Promise<void>;
}) {
  const t = useT();
  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-xl border border-border bg-muted/40 p-1">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => onTab(item.key)}
            className={
              tab === item.key
                ? "min-h-11 flex-1 rounded-lg bg-background text-sm font-semibold shadow-sm"
                : "min-h-11 flex-1 rounded-lg text-sm text-muted-foreground"
            }
          >
            {t(item.label)}
          </button>
        ))}
      </div>
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{empty}</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <InboxItemRow key={item.id} item={item} onApprove={onApprove} onReject={onReject} onAck={onAck} />
          ))}
        </div>
      )}
    </div>
  );
}
