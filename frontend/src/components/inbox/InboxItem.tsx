"use client";

import Link from "next/link";
import type { InboxItem as InboxItemType } from "@/lib/types";
import { useT } from "@/i18n";
import { ApprovalCard } from "./ApprovalCard";

export function InboxItemRow({
  item,
  onApprove,
  onReject,
  onAck,
}: {
  item: InboxItemType;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string, reason: string) => Promise<void>;
  onAck: (id: string) => Promise<void>;
}) {
  const t = useT();
  if (item.tab === "approvals") {
    return <ApprovalCard item={item} onApprove={onApprove} onReject={onReject} />;
  }
  return (
    <article className="rounded-xl border border-border bg-card p-4">
      <p className="text-sm font-semibold">{item.title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{item.summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link href={item.href} className="inline-flex min-h-11 items-center rounded-lg bg-foreground px-3 text-sm font-semibold text-background">
          {t("inbox.open")}
        </Link>
        <Link href={item.sourceHref} className="inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-sm">
          {t("inbox.openSource")}
        </Link>
        <button
          type="button"
          onClick={() => void onAck(item.id)}
          className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm text-muted-foreground hover:text-foreground"
        >
          {t("inbox.ack")}
        </button>
      </div>
    </article>
  );
}
