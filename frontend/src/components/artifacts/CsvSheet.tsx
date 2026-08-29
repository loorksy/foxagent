"use client";

import { useEffect, useMemo, useState } from "react";
import { parseCsv, toCsv } from "@/lib/antArtifact";
import { useT } from "@/i18n";

export function CsvSheet({
  body,
  onChange,
}: {
  body: string;
  onChange?: (body: string) => void;
}) {
  const t = useT();
  const [rows, setRows] = useState(() => parseCsv(body || ""));

  useEffect(() => {
    setRows(parseCsv(body || ""));
  }, [body]);

  const width = useMemo(() => rows.reduce((m, r) => Math.max(m, r.length), 1), [rows]);

  function update(ri: number, ci: number, value: string) {
    const next = rows.map((row, i) => {
      const copy = row.slice();
      while (copy.length < width) copy.push("");
      if (i === ri) copy[ci] = value;
      return copy;
    });
    setRows(next);
    onChange?.(toCsv(next));
  }

  function addRow() {
    const next = [...rows, Array.from({ length: width }, () => "")];
    setRows(next);
    onChange?.(toCsv(next));
  }

  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">{t("artifacts.empty")}</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="fox-scroll min-h-0 flex-1 overflow-auto rounded-md border border-border">
        <table className="art-sheet">
          <thead>
            <tr>
              <th className="w-8" />
              {Array.from({ length: width }, (_, i) => (
                <th key={i}>{String.fromCharCode(65 + (i % 26))}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                <th>{ri + 1}</th>
                {Array.from({ length: width }, (_, ci) => (
                  <td key={ci}>
                    <input value={row[ci] || ""} onChange={(e) => update(ri, ci, e.target.value)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className="self-start rounded-md border border-border px-2 py-1 text-[11px]" onClick={addRow}>
        {t("artifacts.addRow")}
      </button>
    </div>
  );
}
