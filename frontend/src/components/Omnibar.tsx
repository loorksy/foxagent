"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import { ChevronDown, Send, Slash } from "lucide-react";
import { DEFAULT_INSTRUMENTS, MODELS, QUICK_PROMPTS, SLASH_COMMANDS, parsePairShortcut } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace";
import { useChat } from "@/stores/chat";
import { useRecommendations } from "@/stores/recommendations";

function BadgeSelect<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { id: T; label: string }[];
  onChange: (id: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.id === value)?.label || value;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-black/40 px-2 py-1 text-[11px] font-semibold text-gold-400"
      >
        {label ? <span className="text-slate-500">{label}</span> : null}
        {current}
        <ChevronDown className="h-3 w-3 opacity-70" />
      </button>
      {open && (
        <div className="absolute bottom-[calc(100%+6px)] left-0 z-30 min-w-[180px] overflow-hidden rounded-lg border border-white/10 bg-[#0b1220] py-1 shadow-glass">
          {options.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => {
                onChange(o.id);
                setOpen(false);
              }}
              className={cn(
                "block w-full px-3 py-1.5 text-left text-xs hover:bg-white/5",
                o.id === value ? "text-gold-400" : "text-slate-300"
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Omnibar() {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const symbol = useWorkspace((s) => s.symbol);
  const setSymbol = useWorkspace((s) => s.setSymbol);
  const setTimeframe = useWorkspace((s) => s.setTimeframe);
  const clearOverlays = useWorkspace((s) => s.clearOverlays);
  const applyToChart = useWorkspace((s) => s.applyToChart);
  const period = useWorkspace((s) => s.period);
  const model = useChat((s) => s.model);
  const setModel = useChat((s) => s.setModel);
  const streaming = useChat((s) => s.streaming);
  const pushUser = useChat((s) => s.pushUser);
  const startRun = useChat((s) => s.startRun);
  const complete = useChat((s) => s.complete);
  const appendAssistant = useChat((s) => s.appendAssistant);
  const upsert = useRecommendations((s) => s.upsert);
  const slashOpen = value.startsWith("/");
  const slashQuery = value.slice(1).toLowerCase();

  const filteredSlash = useMemo(
    () => SLASH_COMMANDS.filter((c) => c.cmd.slice(1).startsWith(slashQuery) || c.cmd.includes(slashQuery.split(" ")[0])),
    [slashQuery]
  );

  async function submit(raw: string) {
    const text = raw.trim();
    if (!text || streaming) return;
    setValue("");

    if (text.startsWith("/")) {
      const [cmd, ...rest] = text.slice(1).split(/\s+/);
      const arg = rest.join(" ");
      if (cmd === "pair" || cmd === "symbol") {
        const parsed = parsePairShortcut(arg);
        if (parsed) setSymbol(parsed);
        return;
      }
      if (cmd === "timeframe" || cmd === "tf") {
        setTimeframe(arg);
        return;
      }
      if (cmd === "model") {
        const hit = MODELS.find((m) => m.id.includes(arg) || m.label.toLowerCase().includes(arg.toLowerCase()));
        if (hit) setModel(hit.id);
        return;
      }
      if (cmd === "overlay" && arg === "clear") {
        clearOverlays();
        return;
      }
    }

    pushUser(text);
    startRun(`local_${Date.now()}`);
    try {
      await api.streamChat(
        {
          message: text,
          symbol,
          timeframe: period.text,
          model,
        },
        (event) => {
          const p = event.payload || {};
          if (event.type === "phase" && p.phase) useChat.getState().setPhase(p.phase as never);
          if (event.type === "thought" && p.text) useChat.getState().addThought(String(p.text));
          if (event.type === "token" && p.text) useChat.getState().appendToken(String(p.text));
          if (event.type === "assistant" && p.text && !p.recommendationId) {
            useChat.getState().appendAssistant(String(p.text));
          }
          if (event.type === "recommendation" && p.id) {
            const rec = p as unknown as import("@/lib/types").TradeRecommendation;
            upsert(rec);
            applyToChart(rec.klineOverlays || [], rec.focusTimestamp, rec.id);
            if (rec.rationale) useChat.getState().appendAssistant(rec.rationale, rec.id);
          }
        }
      );
    } catch (err) {
      appendAssistant(err instanceof Error ? err.message : "Agent request failed");
    } finally {
      complete();
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void submit(value);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {QUICK_PROMPTS.map((q) => (
          <button
            key={q.label}
            type="button"
            disabled={streaming}
            onClick={() => void submit(q.prompt)}
            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-slate-300 hover:border-gold-500/40 hover:text-gold-400 disabled:opacity-50"
          >
            {q.label}
          </button>
        ))}
      </div>
      <form onSubmit={onSubmit} className="relative">
        {slashOpen && filteredSlash.length > 0 && (
          <div className="absolute bottom-[calc(100%+8px)] left-0 right-0 z-20 overflow-hidden rounded-xl border border-white/10 bg-[#0b1220] shadow-glass">
            {filteredSlash.map((c) => (
              <button
                key={c.cmd}
                type="button"
                onClick={() => {
                  setValue(c.cmd + " ");
                  inputRef.current?.focus();
                }}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-white/5"
              >
                <span className="font-mono text-gold-400">{c.cmd}</span>
                <span className="text-slate-500">{c.hint}</span>
              </button>
            ))}
          </div>
        )}
        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/50 px-2 py-2 focus-within:border-gold-500/40">
          <Slash className="ml-1 h-4 w-4 text-slate-600" />
          <BadgeSelect
            label=""
            value={symbol}
            options={DEFAULT_INSTRUMENTS.map((i) => ({ id: i.ticker, label: i.display }))}
            onChange={(id) => setSymbol(id)}
          />
          <BadgeSelect
            label=""
            value={model}
            options={MODELS.map((m) => ({ id: m.id, label: m.label }))}
            onChange={setModel}
          />
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Ask FoxAgent…  /scan  /pair xauusd  /model sonnet"
            className="min-w-0 flex-1 bg-transparent text-[13px] text-slate-100 outline-none placeholder:text-slate-600"
          />
          <button
            type="submit"
            disabled={streaming || !value.trim()}
            className="flex h-8 w-8 items-center justify-center rounded-xl bg-gold-500 text-ink-950 disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
