"use client";

import {
  Brain,
  CalendarDays,
  Check,
  ChevronDown,
  LineChart,
  Loader2,
  Newspaper,
  Route,
  Scale,
  Shield,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@/stores/chat";
import type { RunStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

function useElapsed(startedAt: number | null, endedAt: number | null, running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);
  if (!startedAt) return 0;
  const end = endedAt || (running ? now : startedAt);
  return Math.max(0, Math.round((end - startedAt) / 1000));
}

function isToolFailed(output: unknown): boolean {
  if (!output || typeof output !== "object") return false;
  const row = output as Record<string, unknown>;
  return row.ok === false || Boolean(row.error);
}

function toolIcon(name?: string) {
  const key = (name || "").toLowerCase();
  if (/candle|chart|draw|screenshot|structure|overlay|ict|price/.test(key)) return LineChart;
  if (/calendar|economic/.test(key)) return CalendarDays;
  if (/news|sentiment|fetch|web/.test(key)) return Newspaper;
  if (/risk|validate/.test(key)) return Shield;
  if (/memory|recall|macro/.test(key)) return Brain;
  return Wrench;
}

function thinkingText(steps: RunStep[]) {
  const parts: string[] = [];
  for (const step of steps) {
    if (step.kind === "thought" && step.text?.trim()) parts.push(step.text.trim());
  }
  return parts.join("\n\n").slice(-6000);
}

function LiveThoughts({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [text]);
  if (!text) return null;
  return (
    <div className="relative overflow-hidden rounded-xl border border-border/50 bg-muted/15">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-6 bg-gradient-to-b from-[var(--background)]/80 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-6 bg-gradient-to-t from-[var(--background)]/80 to-transparent" />
      <div ref={ref} aria-live="polite" role="log" className="max-h-32 overflow-hidden px-3 py-2.5">
        <p className="whitespace-pre-wrap text-[12px] leading-5 text-muted-foreground italic">{text}</p>
      </div>
    </div>
  );
}

function ToolCard({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(false);
  const t = useT();
  const done = step.toolOutput != null;
  const failed = done && isToolFailed(step.toolOutput);
  const Icon = toolIcon(step.toolName);
  const label = step.toolLabel || step.text || step.toolName;
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border bg-card/80",
        failed ? "border-sell/40" : done ? "border-border/60" : "border-info/30"
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-9 w-full items-center gap-2 px-2.5 py-1.5 text-start"
      >
        <span
          className={cn(
            "flex size-6 shrink-0 items-center justify-center rounded-lg",
            failed ? "bg-sell/15 text-sell" : done ? "bg-muted text-muted-foreground" : "bg-info/15 text-info"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </span>
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-foreground">{label}</span>
        <span
          className={cn(
            "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
            failed ? "bg-sell/15 text-sell" : done ? "bg-success/15 text-success" : "bg-info/15 text-info"
          )}
        >
          {failed ? t("run.toolFailed") : done ? t("run.toolDone") : t("run.toolRunning")}
        </span>
        {done ? (
          failed ? null : <Check className="h-3.5 w-3.5 shrink-0 text-success" />
        ) : (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-info" />
        )}
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-1 border-t border-border/40 px-2.5 py-2">
          {step.toolInput != null && (
            <pre className="max-h-28 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-muted-foreground" dir="ltr">
              {JSON.stringify(step.toolInput, null, 2).slice(0, 900)}
            </pre>
          )}
          {step.toolOutput != null && (
            <pre className="max-h-28 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-muted-foreground/80" dir="ltr">
              {JSON.stringify(step.toolOutput, null, 2).slice(0, 900)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function InspectPanel({ steps }: { steps: RunStep[] }) {
  const [open, setOpen] = useState(false);
  const t = useT();
  if (!steps.length) return null;
  return (
    <div className="rounded-xl border border-dashed border-border/50 bg-muted/5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-8 w-full items-center justify-between px-3 py-2 text-[11px] text-muted-foreground hover:text-foreground"
      >
        {t("run.inspect")}
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border/40 px-3 py-2">
          {steps.map((step, index) => (
            <InspectRow key={`${step.kind}-${index}`} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

function InspectRow({ step }: { step: RunStep }) {
  const t = useT();
  if (step.kind === "intent") {
    const key =
      step.intent === "recommendation"
        ? t("run.intent.recommendation")
        : step.intent === "analysis"
          ? t("run.intent.analysis")
          : step.intent === "strategy"
            ? t("run.intent.strategy")
            : t("run.intent.chat");
    return (
      <p className="flex items-center gap-1.5 py-0.5 text-[11px] text-muted-foreground">
        <Route className="h-3 w-3" />
        {t("run.intentLabel")}: <span className="font-medium text-foreground">{key}</span>
      </p>
    );
  }
  if (step.kind === "recall") {
    return (
      <div className="py-0.5">
        <p className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          <Brain className="h-3 w-3" />
          {t("run.memory")}
        </p>
        <p className="whitespace-pre-wrap text-[11px] leading-5 text-warning/90">{(step.text || "").slice(0, 1200)}</p>
      </div>
    );
  }
  if (step.kind === "debate") {
    const roleLabel = step.role === "bull" ? t("run.bull") : step.role === "bear" ? t("run.bear") : step.agent;
    return (
      <div className="rounded-lg border border-border/40 bg-muted/20 px-2.5 py-1.5">
        <p className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          <Scale className="h-3 w-3" />
          {t("run.internalDebate")} — {roleLabel}
        </p>
        <p className="max-h-36 overflow-y-auto whitespace-pre-wrap text-[11px] leading-5 text-foreground/80">{step.text}</p>
      </div>
    );
  }
  return null;
}

export function activityHeadline(steps: RunStep[], live: boolean) {
  const tools = steps.filter((s) => s.kind === "tool");
  const running = [...tools].reverse().find((s) => s.toolOutput == null);
  if (live && running) return running.toolLabel || running.toolName || "";
  return "";
}

export function ChatReasoning({
  steps: stepsProp,
  live,
}: {
  steps?: RunStep[];
  live?: boolean;
}) {
  const storeSteps = useChat((s) => s.steps);
  const streaming = useChat((s) => s.streaming);
  const runStartedAt = useChat((s) => s.runStartedAt);
  const runEndedAt = useChat((s) => s.runEndedAt);
  const isLive = live ?? streaming;
  const steps = stepsProp ?? storeSteps;
  const t = useT();
  const elapsed = useElapsed(isLive ? runStartedAt : steps[0]?.at || null, isLive ? runEndedAt : null, isLive);

  const visible = useMemo(() => steps.filter((s) => s.kind !== "thought" || (s.text || "").trim()), [steps]);
  const tools = useMemo(() => visible.filter((s) => s.kind === "tool"), [visible]);
  const thoughts = useMemo(() => thinkingText(visible), [visible]);
  const inspect = useMemo(() => visible.filter((s) => s.kind === "intent" || s.kind === "recall" || s.kind === "debate"), [visible]);
  const current = activityHeadline(visible, isLive);

  if (!isLive && visible.length === 0) return null;

  const status = isLive
    ? current || (thoughts ? t("run.thinking") : t("run.writing"))
    : t("run.doneThinking");

  return (
    <div className="mb-3">
      <div className="flex min-h-8 items-center gap-2">
        {isLive ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-info" />
        ) : (
          <Check className="h-3.5 w-3.5 shrink-0 text-success" />
        )}
        <p className={cn("min-w-0 flex-1 truncate text-xs font-medium", isLive ? "text-foreground" : "text-muted-foreground")}>
          {status}
          {tools.length > 0 && (
            <span className="text-muted-foreground">
              {" · "}
              {t("run.toolsCount", { n: tools.length })}
            </span>
          )}
          {elapsed > 0 && (
            <span className="ms-1 font-mono text-[11px] tabular-nums text-muted-foreground" dir="ltr">
              {elapsed}s
            </span>
          )}
        </p>
      </div>

      <div className="mt-2 space-y-1.5">
        {isLive && thoughts ? <LiveThoughts text={thoughts} /> : null}
        {!isLive && thoughts ? (
          <details className="rounded-xl border border-border/50 bg-muted/10">
            <summary className="cursor-pointer list-none px-3 py-2 text-[11px] text-muted-foreground hover:text-foreground">
              {t("run.expandActivity")}
            </summary>
            <p className="border-t border-border/40 px-3 py-2 whitespace-pre-wrap text-[12px] leading-5 text-muted-foreground italic">
              {thoughts}
            </p>
          </details>
        ) : null}
        {tools.map((step, index) => (
          <ToolCard key={step.toolId || `${step.toolName}-${index}`} step={step} />
        ))}
        <InspectPanel steps={inspect} />
      </div>
    </div>
  );
}
