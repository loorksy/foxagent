"use client";

import { useT, type MessageKey } from "@/i18n";

type Row = {
  id: string;
  name: string;
  status: string;
  pinned?: boolean;
  winRate?: number | null;
  profitFactor?: number | null;
  maxDrawdownR?: number | null;
  totalTrades?: number | null;
  validatedAt?: string | null;
};

export function LeaderboardTable({ rows }: { rows: Row[] }) {
  const t = useT();
  if (!rows.length) {
    return <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">{t("lab.leaderboardEmpty")}</p>;
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[36rem] text-start text-sm">
        <caption className="sr-only">{t("lab.leaderboard")}</caption>
        <thead className="bg-muted/40 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">{t("lab.name")}</th>
            <th className="px-3 py-2 font-medium">{t("lab.jobStatus")}</th>
            <th className="px-3 py-2 font-medium">WR</th>
            <th className="px-3 py-2 font-medium">PF</th>
            <th className="px-3 py-2 font-medium">DD</th>
            <th className="px-3 py-2 font-medium">{t("backtest.trades")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border">
              <td className="px-3 py-2">
                <p className="font-semibold">{row.name}</p>
                <p className="font-mono text-[11px] text-muted-foreground" dir="ltr">
                  {row.id}
                </p>
              </td>
              <td className="px-3 py-2 text-xs">
                {t(`lab.status.${row.status}` as MessageKey)}
                {row.pinned ? ` · ${t("lab.pin")}` : ""}
              </td>
              <td className="px-3 py-2 font-mono" dir="ltr">
                {row.winRate == null ? "—" : `${(row.winRate * 100).toFixed(0)}%`}
              </td>
              <td className="px-3 py-2 font-mono" dir="ltr">
                {row.profitFactor ?? "—"}
              </td>
              <td className="px-3 py-2 font-mono" dir="ltr">
                {row.maxDrawdownR ?? "—"}
              </td>
              <td className="px-3 py-2 font-mono" dir="ltr">
                {row.totalTrades ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
