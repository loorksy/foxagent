"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function ScansPage() {
  const t = useT();
  const [scans, setScans] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    void api.botScans().then((d) => setScans(d.scans || [])).catch(() => setScans([]));
  }, []);

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium">{t("scans.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("scans.subtitle")}</p>
      {scans.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("scans.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {scans.map((scan) => (
            <li key={String(scan.id)}>
              <Link href={`/scans/${scan.id}`} className="block rounded-xl border border-border bg-card p-4 text-sm">
                <p className="font-mono text-xs" dir="ltr">
                  {String(scan.id)}
                </p>
                <p className="mt-1 text-muted-foreground">
                  {t("scans.counts", { a: Number(scan.acceptedCount || 0), r: Number(scan.rejectedCount || 0) })}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
