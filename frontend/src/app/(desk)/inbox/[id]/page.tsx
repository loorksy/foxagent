"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApprovalCard } from "@/components/inbox/ApprovalCard";
import { InboxItemRow } from "@/components/inbox/InboxItem";
import { api } from "@/lib/api";
import type { InboxItem } from "@/lib/types";
import { useInbox } from "@/stores/inbox";
import { useT } from "@/i18n";

export default function InboxItemRoute() {
  const params = useParams<{ id: string }>();
  const rawId = decodeURIComponent(params.id || "");
  const t = useT();
  const [item, setItem] = useState<InboxItem | null>(null);
  const [missing, setMissing] = useState(false);
  const approve = useInbox((s) => s.approve);
  const reject = useInbox((s) => s.reject);
  const ack = useInbox((s) => s.ack);

  useEffect(() => {
    let live = true;
    void api
      .inboxItem(rawId)
      .then((row) => {
        if (live) setItem(row);
      })
      .catch(() => {
        if (live) setMissing(true);
      });
    return () => {
      live = false;
    };
  }, [rawId]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-5 overflow-y-auto px-4 py-6">
      <Link href="/inbox" className="text-sm text-muted-foreground hover:text-foreground">
        ← {t("inbox.title")}
      </Link>
      {missing ? <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("inbox.notFound")}</p> : null}
      {item && item.tab === "approvals" ? (
        <ApprovalCard item={item} onApprove={approve} onReject={reject} />
      ) : null}
      {item && item.tab !== "approvals" ? (
        <InboxItemRow item={item} onApprove={approve} onReject={reject} onAck={ack} />
      ) : null}
    </div>
  );
}
