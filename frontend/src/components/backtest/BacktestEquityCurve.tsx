"use client";

import { useMemo } from "react";
import { useBacktest } from "@/stores/backtest";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

const W = 640;
const H = 220;
const PAD_X = 10;
const PAD_TOP = 12;
const PAD_BOTTOM = 26;
const LABEL_W = 44;

function niceTicks(min: number, max: number, count = 4): number[] {
  const span = Math.max(max - min, 0.01);
  const rawStep = span / count;
  const mag = 10 ** Math.floor(Math.log10(rawStep));
  const norm = rawStep / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
    out.push(Number(v.toFixed(4)));
  }
  return out;
}

export function BacktestEquityCurve() {
  const report = useBacktest((s) => s.report);
  const trades = report?.trades ?? [];
  const t = useT();
  const points = useMemo(() => {
    let eq = 0;
    return [0, ...(report?.trades ?? []).map((tr) => (eq += tr.pnlR))];
  }, [report]);
  if (points.length < 3) return null;

  const min = Math.min(0, ...points);
  const max = Math.max(0, ...points);
  const span = Math.max(max - min, 0.01);
  const final = points[points.length - 1];
  const positive = final >= 0;

  const plotStart = LABEL_W;
  const plotEnd = W - PAD_X;
  const plotTop = PAD_TOP;
  const plotBottom = H - PAD_BOTTOM;
  const toX = (i: number) => plotStart + (i / (points.length - 1)) * (plotEnd - plotStart);
  const toY = (v: number) => plotBottom - ((v - min) / span) * (plotBottom - plotTop);

  const line = points.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const area = `${line} L${plotEnd},${plotBottom} L${plotStart},${plotBottom} Z`;
  const ticks = niceTicks(min, max);
  const firstDate = trades[0]?.entryTime?.slice(0, 10) ?? "";
  const lastDate = trades[trades.length - 1]?.entryTime?.slice(0, 10) ?? "";

  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("backtest.curve")}</p>
        <p className="text-xs text-muted-foreground">
          {t("backtest.finalR")}{" "}
          <span className={cn("font-mono font-bold tabular-nums", positive ? "text-buy" : "text-sell")} dir="ltr">
            {positive ? "+" : ""}
            {final.toFixed(2)}R
          </span>
        </p>
      </div>
      <div dir="ltr">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className={cn("h-auto w-full", positive ? "text-buy" : "text-sell")}
          role="img"
          aria-label={t("backtest.curve")}
        >
          <defs>
            <linearGradient id="bt-eq-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {ticks.map((v) => (
            <g key={v} className="text-border">
              <line
                x1={plotStart}
                x2={plotEnd}
                y1={toY(v)}
                y2={toY(v)}
                stroke="currentColor"
                strokeWidth="1"
                strokeDasharray={v === 0 ? "0" : "3 4"}
                opacity={v === 0 ? 0.9 : 0.5}
              />
              <text
                x={plotStart - 6}
                y={toY(v) + 3}
                textAnchor="end"
                className="fill-muted-foreground font-mono text-[10px] tabular-nums"
              >
                {v}R
              </text>
            </g>
          ))}
          <path d={area} fill="url(#bt-eq-fill)" stroke="none" />
          <path d={line} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
          <circle cx={toX(points.length - 1)} cy={toY(final)} r="3" fill="currentColor" />
          <text x={plotStart} y={H - 8} textAnchor="start" className="fill-muted-foreground font-mono text-[10px]">
            {firstDate}
          </text>
          <text x={plotEnd} y={H - 8} textAnchor="end" className="fill-muted-foreground font-mono text-[10px]">
            {lastDate}
          </text>
        </svg>
      </div>
    </section>
  );
}
