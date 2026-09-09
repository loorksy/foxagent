"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function ScanDetailPage() {
  const t = useT();
  const params = useParams<{ id: string }>();
  const [scan, setScan] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.botScan(decodeURIComponent(params.id || "")).then(setScan).catch(() => setScan(null));
  }, [params.id]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <Link href="/scans" className="text-sm text-muted-foreground">
        ← {t("scans.title")}
      </Link>
      {!scan ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("scans.empty")}</p>
      ) : (
        <pre className="overflow-x-auto rounded-xl border border-border bg-card p-4 text-xs" dir="ltr">
          {JSON.stringify(scan, null, 2)}
        </pre>
      )}
    </div>
  );
}
