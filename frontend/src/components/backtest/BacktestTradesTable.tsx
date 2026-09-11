"use client";

import { useBacktest } from "@/stores/backtest";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import type { BacktestTrade } from "@/lib/types";

const MAX_ROWS = 80;

function fmtTime(iso?: string) {
  return iso ? iso.replace("T", " ").slice(0, 16) : "—";
}

function DirectionChip({ direction }: { direction: BacktestTrade["direction"] }) {
  const t = useT();
  const buy = direction === "buy";
  return (
    <span
      className={cn(
        "inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
        buy ? "border-buy/45 bg-buy/10 text-buy" : "border-sell/40 bg-sell/10 text-sell"
      )}
    >
      {t(buy ? "rec.buy" : "rec.sell")}
    </span>
  );
}

function RValue({ value }: { value: number }) {
  return (
    <span className={cn("font-mono font-bold tabular-nums", value >= 0 ? "text-buy" : "text-sell")} dir="ltr">
      {value >= 0 ? "+" : ""}
      {value.toFixed(2)}R
    </span>
  );
}

export function BacktestTradesTable() {
  const report = useBacktest((s) => s.report);
  const trades = report?.trades ?? [];
  const t = useT();
  if (!trades.length) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-8 text-center text-sm text-muted-foreground">
        {t("backtest.empty")}
      </p>
    );
  }
  const shown = trades.slice(0, MAX_ROWS);
  const strategyLabel = (id: string) => (id.startsWith("gold_") ? t(`bot.strategy.${id}` as MessageKey) : id);

  return (
    <section className="space-y-2">
      {/* Desktop table */}
      <div className="hidden overflow-x-auto rounded-xl border border-border bg-card md:block">
        <table className="w-full min-w-[44rem] text-sm">
          <thead className="bg-muted/40 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.strategy")}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.direction")}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.entry")}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.exit")}</th>
              <th className="px-3 py-2.5 text-start font-semibold">{t("backtest.reason")}</th>
              <th className="px-3 py-2.5 text-end font-semibold">R</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((tr, i) => (
              <tr key={`${tr.entryTime}-${i}`} className="border-t border-border/60 even:bg-muted/20">
                <td className="px-3 py-2">{strategyLabel(tr.strategyId)}</td>
                <td className="px-3 py-2">
                  <DirectionChip direction={tr.direction} />
                </td>
                <td className="px-3 py-2 font-mono text-[11px] tabular-nums" dir="ltr">
                  <span className="text-muted-foreground">{fmtTime(tr.entryTime)}</span>{" "}
                  <span className="font-semibold">{tr.entryPrice}</span>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] tabular-nums" dir="ltr">
                  <span className="text-muted-foreground">{fmtTime(tr.exitTime)}</span>{" "}
                  <span className="font-semibold">{tr.exitPrice}</span>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground" dir="ltr">
                  {tr.exitReason}
                </td>
                <td className="px-3 py-2 text-end">
                  <RValue value={tr.pnlR} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <ul className="space-y-2 md:hidden">
        {shown.map((tr, i) => (
          <li key={`${tr.entryTime}-m-${i}`} className="rounded-xl border border-border bg-card p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <DirectionChip direction={tr.direction} />
                <span className="text-sm font-semibold">{strategyLabel(tr.strategyId)}</span>
              </div>
              <RValue value={tr.pnlR} />
            </div>
            <dl className="mt-2 space-y-1 text-[11px]">
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{t("backtest.entry")}</dt>
                <dd className="font-mono tabular-nums" dir="ltr">
                  {fmtTime(tr.entryTime)} · {tr.entryPrice}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{t("backtest.exit")}</dt>
                <dd className="font-mono tabular-nums" dir="ltr">
                  {fmtTime(tr.exitTime)} · {tr.exitPrice}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{t("backtest.reason")}</dt>
                <dd className="font-mono" dir="ltr">
                  {tr.exitReason}
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>

      {trades.length > MAX_ROWS ? (
        <p className="text-center text-[11px] text-muted-foreground">
          {t("backtest.showingOf", { shown: MAX_ROWS, total: trades.length })}
        </p>
      ) : null}
    </section>
  );
}
