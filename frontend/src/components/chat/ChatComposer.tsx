"use client";

import { FormEvent, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { DEFAULT_INSTRUMENTS, MODELS, QUICK_PROMPTS, SLASH_COMMANDS } from "@/lib/constants";
import { sendAgentMessage } from "@/lib/agentSend";
import { useChat } from "@/stores/chat";
import { useWorkspace } from "@/stores/workspace";
import { cn } from "@/lib/utils";
import { useT, type MessageKey } from "@/i18n";

export function ChatComposer({ hero = false }: { hero?: boolean }) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const streaming = useChat((s) => s.streaming);
  const model = useChat((s) => s.model);
  const setModel = useChat((s) => s.setModel);
  const symbol = useWorkspace((s) => s.symbol);
  const setSymbol = useWorkspace((s) => s.setSymbol);
  const period = useWorkspace((s) => s.period);
  const setTimeframe = useWorkspace((s) => s.setTimeframe);
  const t = useT();
  const slashOpen = value.startsWith("/");
  const slashQuery = value.slice(1).toLowerCase();
  const filteredSlash = useMemo(
    () => SLASH_COMMANDS.filter((c) => c.cmd.slice(1).startsWith(slashQuery.split(" ")[0])),
    [slashQuery]
  );

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 148)}px`;
  }, [value]);

  function onSubmit(e?: FormEvent) {
    e?.preventDefault();
    const text = value;
    setValue("");
    void sendAgentMessage(text);
  }

  return (
    <div className="w-full">
      {hero && (
        <div className="mb-3 flex flex-wrap justify-center gap-1.5">
          {QUICK_PROMPTS.map((q) => (
            <button
              key={q.id}
              type="button"
              disabled={streaming}
              onClick={() => void sendAgentMessage(q.prompt)}
              className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              {t(`quick.${q.id}` as MessageKey)}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={onSubmit} className="relative">
        {slashOpen && filteredSlash.length > 0 && (
          <div className="absolute inset-x-0 bottom-[calc(100%+8px)] z-20 overflow-hidden rounded-xl border border-border bg-card">
            {filteredSlash.map((c) => (
              <button
                key={c.cmd}
                type="button"
                onClick={() => setValue(`${c.cmd} `)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-muted"
              >
                <span className="font-mono">{c.cmd}</span>
                <span className="text-muted-foreground">{t(c.hintKey)}</span>
              </button>
            ))}
          </div>
        )}
        <div className="rounded-2xl border border-border bg-[var(--chat-input)] px-2 py-2 focus-within:ring-1 focus-within:ring-ring">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit();
              }
            }}
            placeholder={t("chat.placeholder")}
            className="max-h-36 min-h-10 w-full resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center gap-1.5 px-1 pb-0.5">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="max-w-28 truncate rounded-full border border-border bg-transparent px-2 py-1 text-[11px] font-medium"
            >
              {DEFAULT_INSTRUMENTS.map((i) => (
                <option key={i.ticker} value={i.ticker}>
                  {i.display}
                </option>
              ))}
            </select>
            <select
              value={period.text}
              onChange={(e) => setTimeframe(e.target.value)}
              className="rounded-full border border-border bg-transparent px-2 py-1 text-[11px] font-medium"
            >
              {["1m", "5m", "15m", "30m", "1H", "4H", "1D"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="max-w-40 truncate rounded-full border border-border bg-transparent px-2 py-1 text-[11px] font-medium"
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            <button
              type={streaming ? "button" : "submit"}
              onClick={streaming ? () => useChat.getState().complete() : undefined}
              disabled={!streaming && !value.trim()}
              className={cn(
                "ms-auto flex size-8 items-center justify-center rounded-full disabled:opacity-40",
                streaming ? "bg-foreground text-background" : "bg-foreground text-background"
              )}
              aria-label={streaming ? t("chat.stop") : t("chat.send")}
            >
              {streaming ? <Square className="h-3.5 w-3.5" /> : <ArrowUp className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </form>
      <p className="mt-1.5 px-2 text-center text-[10px] leading-4 text-muted-foreground/60">
        {t("chat.disclaimer")}
      </p>
    </div>
  );
}
