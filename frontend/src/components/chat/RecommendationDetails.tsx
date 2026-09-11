"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CandlestickChart, ChevronDown, LineChart, Newspaper, Scale, ShieldCheck, X } from "lucide-react";
import { useRecommendations } from "@/stores/recommendations";
import { useWorkspace } from "@/stores/workspace";
import { cn, formatPrice } from "@/lib/utils";
import { displaySymbol } from "@/lib/constants";
import { recStatusKey, useT } from "@/i18n";

function Section({
  title,
  icon: Icon,
  text,
  defaultOpen = false,
}: {
  title: string;
  icon: typeof LineChart;
  text?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!text?.trim()) return null;
  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-10 w-full items-center gap-2 px-3 py-2 text-start text-xs font-semibold text-foreground hover:bg-muted/40"
      >
        <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1">{title}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-border/50 px-3 py-2.5">
          <p className="whitespace-pre-wrap text-[13px] leading-6 text-foreground/85">{text.trim()}</p>
        </div>
      )}
    </div>
  );
}

export function RecommendationDetails({ recId }: { recId: string }) {
  const recs = useRecommendations((s) => s.items);
  const applyToChart = useWorkspace((s) => s.applyToChart);
  const router = useRouter();
  const pathname = usePathname() || "/agents";
  const t = useT();
  const rec = useMemo(() => recs.find((r) => r.id === recId), [recs, recId]);

  const close = () => router.replace(pathname, { scroll: false });

  if (!rec) {
    return (
      <div className="flex h-full flex-col">
        <PanelHeader title={t("recDetails.title")} onClose={close} />
        <p className="p-4 text-sm text-muted-foreground">{t("recDetails.missing")}</p>
      </div>
    );
  }

  const buy = rec.tradeSetup.action === "BUY";
  const analysis = rec.analysis || {};
  const debateText = [
    analysis.bull ? `▲ ${t("run.bull")}\n${analysis.bull.trim()}` : "",
    analysis.bear ? `▼ ${t("run.bear")}\n${analysis.bear.trim()}` : "",
  ]
    .filter(Boolean)
    .join("\n\n———\n\n");
  const hasAnalysis = Boolean(analysis.technical || analysis.fundamental || debateText || analysis.risk);

  return (
    <div className="flex h-full flex-col">
      <PanelHeader title={t("recDetails.title")} onClose={close} />
      <div className="fox-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <div className={cn("rounded-xl border border-border/60 p-3", buy ? "bg-buy/10" : "bg-sell/10")}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className={cn("font-mono text-lg font-extrabold", buy ? "text-buy" : "text-sell")} dir="ltr">
              {displaySymbol(rec.symbol)} · {buy ? t("rec.buy") : t("rec.sell")}
            </p>
            <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground">
              {t(recStatusKey(rec.status))}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Metric label={t("rec.entry")} value={rec.tradeSetup.entryPrice} />
            <Metric label={t("rec.stopLoss")} value={rec.tradeSetup.stopLoss} tone="text-sell" />
            {rec.tradeSetup.takeProfitLevels.slice(0, 3).map((tp) => (
              <Metric key={tp.level} label={t("rec.target", { n: tp.level })} value={tp.price} tone="text-buy" />
            ))}
            <div>
              <p className="text-[10px] text-muted-foreground">R:R</p>
              <p className="font-mono text-sm font-bold text-foreground" dir="ltr">
                {rec.tradeSetup.riskRewardRatio.toFixed(2)}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => applyToChart(rec.klineOverlays || [], rec.focusTimestamp, rec.id)}
            className="mt-2 inline-flex items-center gap-1 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-foreground hover:bg-muted"
          >
            <CandlestickChart className="h-3 w-3" />
            {t("rec.showOnChart")}
          </button>
        </div>

        <div className="rounded-xl border border-border/60 bg-card p-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("recDetails.rationale")}</p>
          <p className="whitespace-pre-wrap text-[13px] leading-6 text-foreground/90">{rec.rationale}</p>
          {rec.confluence.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {rec.confluence.map((c) => (
                <span key={c} className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>

        {hasAnalysis ? (
          <>
            <Section title={t("recDetails.technical")} icon={LineChart} text={analysis.technical} defaultOpen />
            <Section title={t("recDetails.fundamental")} icon={Newspaper} text={analysis.fundamental} />
            <Section title={t("recDetails.debate")} icon={Scale} text={debateText} />
            <Section title={t("recDetails.risk")} icon={ShieldCheck} text={analysis.risk} />
          </>
        ) : (
          <p className="px-1 text-xs text-muted-foreground">{t("recDetails.missing")}</p>
        )}
      </div>
    </div>
  );
}

function PanelHeader({ title, onClose }: { title: string; onClose: () => void }) {
  const t = useT();
  return (
    <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <button
        type="button"
        onClick={onClose}
        className="flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label={t("recDetails.close")}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function Metric({ label, value, tone = "text-foreground" }: { label: string; value: number; tone?: string }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className={cn("font-mono text-sm font-bold tabular-nums", tone)} dir="ltr">
        {formatPrice(value, value > 50 ? 2 : 5)}
      </p>
    </div>
  );
}
