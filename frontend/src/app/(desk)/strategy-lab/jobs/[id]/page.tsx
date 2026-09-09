"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function StrategyJobPage() {
  const t = useT();
  const params = useParams<{ id: string }>();
  const [job, setJob] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.labJob(decodeURIComponent(params.id || "")).then(setJob).catch(() => setJob(null));
  }, [params.id]);

  const attempts = (job?.attempts as Array<Record<string, unknown>>) || [];

  return (
    <div className="fox-scroll mx-auto w-full max-w-3xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <Link href="/strategy-lab" className="text-sm text-muted-foreground">
        ← {t("lab.title")}
      </Link>
      <h1 className="font-serif text-2xl font-medium">{t("lab.jobTitle")}</h1>
      {!job ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("lab.jobEmpty")}</p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {t("lab.jobStatus")}: {String(job.status)} · {attempts.length}/{String(job.maxAttempts || 8)}
          </p>
          {attempts.map((a) => (
            <article key={String(a.n)} className="rounded-xl border border-border bg-card p-4 text-sm">
              <p className="font-semibold">
                {t("lab.attempt", { n: Number(a.n) })} — {String(a.change)}
              </p>
              <p className="mt-1 font-mono text-xs" dir="ltr">
                {a.passed ? "pass" : "fail"} · {JSON.stringify(a.report || {})}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
