"use client";

import { Brain, Check, ChevronDown, Loader2, Route, Scale, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@/stores/chat";
import type { RunStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

const AGENT_LABELS: Record<string, string> = {
  TechnicalAgent: "TechnicalAgent",
  FundamentalAgent: "FundamentalAgent",
  RiskManagerAgent: "RiskManagerAgent",
  BullResearcher: "BullResearcher",
  BearResearcher: "BearResearcher",
  FoxAgent: "FoxAgent",
  StrategyAgent: "StrategyAgent",
};

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

function LiveThinkingCard({ steps }: { steps: RunStep[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const text = useMemo(() => {
    const parts: string[] = [];
    for (const step of steps) {
      if (step.kind === "thought" && step.text?.trim()) {
        parts.push(step.text.trim());
      }
    }
    return parts.join("\n\n").slice(-6000);
  }, [steps]);

  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [text]);

  if (!text) return null;
  return (
    <div className="relative mt-2 overflow-hidden rounded-xl border border-border/60 bg-muted/20" style={{ height: 140 }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-10 bg-gradient-to-b from-background/90 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-10 bg-gradient-to-t from-background/90 to-transparent" />
      <div ref={ref} aria-live="polite" role="log" className="h-full overflow-hidden px-3 py-2">
        <p className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-muted-foreground">{text}</p>
      </div>
    </div>
  );
}

function ToolStep({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(false);
  const done = step.toolOutput != null;
  return (
    <div className="rounded-lg border border-border/50 bg-background/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-8 w-full items-center gap-2 px-2.5 py-1.5 text-start font-mono text-[11px] text-foreground hover:bg-muted/40"
      >
        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate">
          <span className="text-muted-foreground">{step.agent}</span> · {step.toolName}
        </span>
        {done ? (
          <Check className="h-3 w-3 shrink-0 text-success" />
        ) : (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
        )}
        <ChevronDown className={cn("h-3 w-3 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-1 border-t border-border/40 px-2.5 py-1.5">
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

function StepBody({ step }: { step: RunStep }) {
  const t = useT();
  if (step.kind === "tool") return <ToolStep step={step} />;
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
        <p className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-warning/90">{(step.text || "").slice(0, 1200)}</p>
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
  return (
    <div className="py-0.5">
      <p className="text-[10px] font-semibold text-muted-foreground">{AGENT_LABELS[step.agent || ""] || step.agent}</p>
      <p
        className={cn(
          "max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-5",
          step.channel === "thinking" ? "text-muted-foreground/80 italic" : "text-foreground/85"
        )}
      >
        {(step.text || "").slice(-3000)}
      </p>
    </div>
  );
}

export function ChatReasoning() {
  const steps = useChat((s) => s.steps);
  const streaming = useChat((s) => s.streaming);
  const runStartedAt = useChat((s) => s.runStartedAt);
  const runEndedAt = useChat((s) => s.runEndedAt);
  const [open, setOpen] = useState(false);
  const t = useT();
  const elapsed = useElapsed(runStartedAt, runEndedAt, streaming);

  const visibleSteps = useMemo(() => steps.filter((s) => s.kind !== "thought" || (s.text || "").trim()), [steps]);
  const latestTool = useMemo(() => [...visibleSteps].reverse().find((s) => s.kind === "tool"), [visibleSteps]);

  if (!streaming && visibleSteps.length === 0) return null;

  const header = streaming ? (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      <span className="animate-pulse font-medium">{t("run.thinking")}</span>
      {elapsed > 0 && (
        <span className="font-mono text-[11px] tabular-nums" dir="ltr">
          {elapsed}s
        </span>
      )}
    </div>
  ) : (
    <span className="text-xs font-medium text-muted-foreground">
      {t("run.doneThinking")}
      {visibleSteps.length > 0 && ` · ${t("run.stepsCount", { n: visibleSteps.length })}`}
      {elapsed > 0 && ` · ${elapsed}s`}
    </span>
  );

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-8 w-full items-center gap-1.5 text-start hover:opacity-80"
      >
        <span className="min-w-0 flex-1">{header}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {streaming && !open && (
        <>
          <LiveThinkingCard steps={steps} />
          {latestTool && (
            <p className="mt-1.5 flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
              <Wrench className="h-3 w-3" />
              {latestTool.agent} · {latestTool.toolName}
              {latestTool.toolOutput != null ? <Check className="h-3 w-3 text-success" /> : <Loader2 className="h-3 w-3 animate-spin" />}
            </p>
          )}
        </>
      )}

      {open && (
        <div className="mt-2 flex flex-col rounded-xl border border-border/50 bg-muted/10 px-3 py-2">
          {visibleSteps.map((step, index) => (
            <div key={index} className="flex gap-2.5">
              <div className="flex flex-col items-center pt-2">
                <div className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/50" />
                {index < visibleSteps.length - 1 && <div className="w-px min-h-0 flex-1 bg-border" />}
              </div>
              <div className="min-w-0 flex-1 pb-2">
                <StepBody step={step} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
