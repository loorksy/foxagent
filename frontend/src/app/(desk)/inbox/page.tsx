"use client";

import { useEffect } from "react";
import { DeskStatusCard } from "@/components/desk/DeskStatusCard";
import { InboxList } from "@/components/inbox/InboxList";
import { useInbox } from "@/stores/inbox";
import { useT } from "@/i18n";

export default function InboxRoute() {
  const items = useInbox((s) => s.items);
  const tab = useInbox((s) => s.tab);
  const desk = useInbox((s) => s.desk);
  const error = useInbox((s) => s.error);
  const load = useInbox((s) => s.load);
  const setTab = useInbox((s) => s.setTab);
  const approve = useInbox((s) => s.approve);
  const reject = useInbox((s) => s.reject);
  const ack = useInbox((s) => s.ack);
  const t = useT();
  const empty =
    tab === "approvals" ? t("inbox.emptyApprovals") : tab === "alerts" ? t("inbox.emptyAlerts") : t("inbox.empty");

  useEffect(() => {
    void load("inbox");
  }, [load]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-5 overflow-y-auto px-4 py-6">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight">{t("inbox.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("inbox.subtitle")}</p>
      </div>
      <DeskStatusCard desk={desk} />
      {error ? <p className="text-sm text-sell">{error}</p> : null}
      <InboxList
        items={items}
        tab={tab}
        onTab={(next) => {
          setTab(next);
          void load(next);
        }}
        empty={empty}
        onApprove={approve}
        onReject={reject}
        onAck={ack}
      />
    </div>
  );
}
