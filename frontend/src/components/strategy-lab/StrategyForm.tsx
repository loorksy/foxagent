"use client";

import { FormEvent, useState } from "react";
import { useStrategyLab } from "@/stores/strategyLab";
import { useT, type MessageKey } from "@/i18n";

const TFS = ["M15", "H1", "H4", "D"] as const;
const FLAGS = ["asian_sweep", "fvg_exists", "bos_confirmed", "breakout", "trend", "reversal", "scalp"] as const;

export function StrategyForm() {
  const t = useT();
  const create = useStrategyLab((s) => s.create);
  const setTab = useStrategyLab((s) => s.setTab);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [direction, setDirection] = useState<"buy" | "sell" | "both">("both");
  const [timeframes, setTimeframes] = useState<string[]>(["M15"]);
  const [stopRule, setStopRule] = useState("swing ± ATR");
  const [tp1, setTp1] = useState(1.5);
  const [tp2, setTp2] = useState(3);
  const [hold, setHold] = useState(48);
  const [flags, setFlags] = useState<string[]>(["fvg_exists"]);

  function toggleTf(tf: string) {
    setTimeframes((cur) => (cur.includes(tf) ? cur.filter((x) => x !== tf) : [...cur, tf]));
  }

  function toggleFlag(flag: string) {
    setFlags((cur) => (cur.includes(flag) ? cur.filter((x) => x !== flag) : [...cur, flag]));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const entry_conditions: Record<string, boolean> = {};
    for (const flag of flags) entry_conditions[flag] = true;
    const created = await create({
      name,
      description,
      direction,
      timeframes: timeframes.length ? timeframes : ["M15"],
      stop_rule: stopRule,
      tp1_r: tp1,
      tp2_r: tp2,
      max_holding_bars: hold,
      entry_conditions,
      source: "manual",
    });
    if (created) {
      setName("");
      setDescription("");
      setTab("library");
    }
  }

  return (
    <form className="space-y-4 rounded-xl border border-border bg-card p-4" onSubmit={(e) => void onSubmit(e)}>
      <label className="block text-xs text-muted-foreground">
        {t("lab.name")}
        <input className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label className="block text-xs text-muted-foreground">
        {t("lab.description")}
        <textarea className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <div className="text-xs text-muted-foreground">
        {t("lab.timeframes")}
        <div className="mt-1 flex flex-wrap gap-2">
          {TFS.map((tf) => (
            <label key={tf} className="flex items-center gap-1 rounded-full border border-border px-2 py-1">
              <input type="checkbox" checked={timeframes.includes(tf)} onChange={() => toggleTf(tf)} />
              <span dir="ltr">{tf}</span>
            </label>
          ))}
        </div>
      </div>
      <label className="block text-xs text-muted-foreground">
        {t("lab.direction")}
        <select className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" value={direction} onChange={(e) => setDirection(e.target.value as "buy" | "sell" | "both")}>
          <option value="both">{t("lab.direction.both")}</option>
          <option value="buy">{t("lab.direction.buy")}</option>
          <option value="sell">{t("lab.direction.sell")}</option>
        </select>
      </label>
      <div className="text-xs text-muted-foreground">
        {t("lab.conditions")}
        <div className="mt-1 flex flex-wrap gap-2">
          {FLAGS.map((flag) => (
            <label key={flag} className="flex items-center gap-1 rounded-full border border-border px-2 py-1">
              <input type="checkbox" checked={flags.includes(flag)} onChange={() => toggleFlag(flag)} />
              {t(`lab.cond.${flag}` as MessageKey)}
            </label>
          ))}
        </div>
      </div>
      <label className="block text-xs text-muted-foreground">
        {t("lab.stop")}
        <input className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" value={stopRule} onChange={(e) => setStopRule(e.target.value)} />
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-xs text-muted-foreground">
          {t("lab.tp1")}
          <input className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm" type="number" step="0.1" value={tp1} onChange={(e) => setTp1(Number(e.target.value) || 1.5)} />
        </label>
        <label className="text-xs text-muted-foreground">
          {t("lab.tp2")}
          <input className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm" type="number" step="0.1" value={tp2} onChange={(e) => setTp2(Number(e.target.value) || 3)} />
        </label>
        <label className="text-xs text-muted-foreground">
          {t("lab.hold")}
          <input className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm" type="number" value={hold} onChange={(e) => setHold(Number(e.target.value) || 48)} />
        </label>
      </div>
      <button type="submit" className="rounded-lg border border-border px-3 py-2 text-sm font-semibold">
        {t("lab.saveDraft")}
      </button>
    </form>
  );
}
