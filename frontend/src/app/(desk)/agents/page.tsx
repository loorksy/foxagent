"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function AgentsIndexPage() {
  const router = useRouter();
  const t = useT();

  useEffect(() => {
    let cancelled = false;
    void api
      .createSession()
      .then((session) => {
        if (!cancelled) router.replace(`/agents/${session.id}`);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
      {t("chats.creating")}
    </div>
  );
}
