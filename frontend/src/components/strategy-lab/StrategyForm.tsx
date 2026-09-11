"use client";

import { FormEvent, KeyboardEvent, useState } from "react";
import { useStrategyLab } from "@/stores/strategyLab";
import { api } from "@/lib/api";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";

const TFS = ["M15", "H1", "H4", "D"] as const;
const FLAGS = ["asian_sweep", "fvg_exists", "bos_confirmed", "breakout", "trend", "reversal", "scalp"] as const;
const SESSIONS = ["asia", "london", "ny", "london_ny_overlap", "london_close"] as const;

const CODE_TEMPLATE = `# استراتيجية بايثون — الذهب فقط (XAU_USD)
# تُستدعى on_bar(ctx) عند كل شمعة:
#   ctx.candles — قائمة الشموع حتى الشمعة الحالية (timestamp/open/high/low/close/volume)
#   ctx.i — رقم الشمعة الحالية
#   ctx.params — إعدادات إضافية (tp1_r/tp2_r/timeframe...)
# أعِد None لعدم التداول، أو dict بالإشارة:
#   {"action": "BUY" أو "SELL", "entry": ..., "stopLoss": ..., "tp1": ..., "tp2": ..., "note": "..."}
# المسموح استيراده: math, statistics, json فقط — لا شبكة ولا ملفات.

def on_bar(ctx):
    if ctx.i < 20:
        return None
    closes = [c["close"] for c in ctx.candles[-20:]]
    fast = sum(closes[-5:]) / 5
    slow = sum(closes) / 20
    last = ctx.candles[-1]
    if fast > slow:
        return {
            "action": "BUY",
            "entry": last["close"],
            "stopLoss": last["close"] - 3.0,
            "tp1": last["close"] + 3.0,
            "tp2": last["close"] + 6.0,
            "note": "تقاطع متوسطات بسيط",
        }
    return None
`;

export function StrategyForm() {
  const t = useT();
  const create = useStrategyLab((s) => s.create);
  const setTab = useStrategyLab((s) => s.setTab);
  const [mode, setMode] = useState<"dsl" | "python">("dsl");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [direction, setDirection] = useState<"buy" | "sell" | "both">("both");
  const [timeframes, setTimeframes] = useState<string[]>(["M15"]);
  const [stopRule, setStopRule] = useState("swing ± ATR");
  const [tp1, setTp1] = useState(1.5);
  const [tp2, setTp2] = useState(3);
  const [hold, setHold] = useState(48);
  const [flags, setFlags] = useState<string[]>(["fvg_exists"]);
  const [sessions, setSessions] = useState<string[]>(["asia", "london", "ny", "london_ny_overlap", "london_close"]);
  const [code, setCode] = useState(CODE_TEMPLATE);
  const [lint, setLint] = useState<{ ok: boolean; error?: string | null } | null>(null);
  const [linting, setLinting] = useState(false);

  function toggleTf(tf: string) {
    setTimeframes((cur) => (cur.includes(tf) ? cur.filter((x) => x !== tf) : [...cur, tf]));
  }

  function toggleFlag(flag: string) {
    setFlags((cur) => (cur.includes(flag) ? cur.filter((x) => x !== flag) : [...cur, flag]));
  }

  function onCodeKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const el = e.currentTarget;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const next = `${code.slice(0, start)}    ${code.slice(end)}`;
    setCode(next);
    requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = start + 4;
    });
  }

  async function onLint() {
    setLinting(true);
    try {
      const result = await api.lintStrategyCode(code);
      setLint(result);
    } catch {
      setLint({ ok: false, error: "lint failed" });
    } finally {
      setLinting(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const tfs = timeframes.length ? timeframes : ["M15"];
    const body: Record<string, unknown> =
      mode === "python"
        ? { name, description, timeframes: tfs, kind: "python", code, source: "manual" }
        : {
            name,
            description,
            direction,
            timeframes: tfs,
            stop_rule: stopRule,
            tp1_r: tp1,
            tp2_r: tp2,
            max_holding_bars: hold,
            entry_conditions: Object.fromEntries(flags.map((flag) => [flag, true])),
            sessions,
            source: "manual",
          };
    const created = await create(body);
    if (created) {
      setName("");
      setDescription("");
      setLint(null);
      setTab("library");
    }
  }

  return (
    <form className="space-y-4 rounded-xl border border-border bg-card p-4" onSubmit={(e) => void onSubmit(e)}>
      <div className="flex flex-wrap gap-2">
        {(["dsl", "python"] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMode(item)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs font-semibold",
              mode === item ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            {t(item === "dsl" ? "lab.dslMode" : "lab.codeMode")}
          </button>
        ))}
      </div>
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
      {mode === "python" ? (
        <>
          <p className="text-xs text-muted-foreground">{t("lab.codeTemplateHint")}</p>
          <textarea
            className="w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-xs leading-relaxed"
            dir="ltr"
            rows={20}
            spellCheck={false}
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              setLint(null);
            }}
            onKeyDown={onCodeKeyDown}
            data-testid="strategy-code-editor"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={linting}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
              onClick={() => void onLint()}
            >
              {t("lab.lint")}
            </button>
            {lint ? (
              lint.ok ? (
                <span className="text-xs text-buy">{t("lab.lintOk")}</span>
              ) : (
                <span className="text-xs text-sell" dir="ltr">
                  {t("lab.lintError")}: {lint.error}
                </span>
              )
            ) : null}
          </div>
        </>
      ) : (
        <>
          <label className="block text-xs text-muted-foreground">
            {t("lab.direction")}
            <select className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm" value={direction} onChange={(e) => setDirection(e.target.value as "buy" | "sell" | "both")}>
              <option value="both">{t("lab.direction.both")}</option>
              <option value="buy">{t("lab.direction.buy")}</option>
              <option value="sell">{t("lab.direction.sell")}</option>
            </select>
          </label>
          <div className="text-xs text-muted-foreground">
            {t("lab.sessions")}
            <div className="mt-1 flex flex-wrap gap-2">
              {SESSIONS.map((session) => (
                <label key={session} className="flex items-center gap-1 rounded-full border border-border px-2 py-1">
                  <input
                    type="checkbox"
                    checked={sessions.includes(session)}
                    onChange={() => setSessions((cur) => (cur.includes(session) ? cur.filter((x) => x !== session) : [...cur, session]))}
                  />
                  {t(`lab.session.${session}` as MessageKey)}
                </label>
              ))}
            </div>
          </div>
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
        </>
      )}
      <button type="submit" className="rounded-lg border border-border px-3 py-2 text-sm font-semibold">
        {t("lab.saveDraft")}
      </button>
    </form>
  );
}
