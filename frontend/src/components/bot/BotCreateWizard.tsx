"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Bell, FlaskConical, LineChart, X, Zap } from "lucide-react";
import { api } from "@/lib/api";
import type { BotInstanceCreatePayload, BotInstanceType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useStrategyLab } from "@/stores/strategyLab";
import { useT, type MessageKey } from "@/i18n";

const AGENTS = ["multi_strategy", "pattern_notes", "news_candle"] as const;
const SESSIONS = ["london", "ny", "asian"] as const;

const BOT_TYPES: BotInstanceType[] = ["strategy", "quant", "alerts", "execution"];

const TYPE_ICONS = {
  strategy: LineChart,
  quant: FlaskConical,
  alerts: Bell,
  execution: Zap,
} as const;

const TYPE_COLORS: Record<BotInstanceType, string> = {
  strategy: "border-blue-500/40 hover:border-blue-500/70",
  quant: "border-purple-500/40 hover:border-purple-500/70",
  alerts: "border-amber-500/40 hover:border-amber-500/70",
  execution: "border-red-500/40 hover:border-red-500/70",
};

function sessionKey(session: string): MessageKey {
  const id = session === "asian" ? "asia" : session;
  return `lab.session.${id}` as MessageKey;
}

function toggle(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
}

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: BotInstanceCreatePayload) => Promise<boolean>;
  error?: string;
};

export function BotCreateWizard({ open, onClose, onSubmit, error }: Props) {
  const t = useT();
  const labItems = useStrategyLab((s) => s.items);
  const loadLab = useStrategyLab((s) => s.load);

  const [step, setStep] = useState(0);
  const [mt5Connected, setMt5Connected] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [type, setType] = useState<BotInstanceType>("strategy");
  const [name, setName] = useState("");
  const [scanIntervalSeconds, setScanIntervalSeconds] = useState(60);
  const [agents, setAgents] = useState<string[]>([...AGENTS]);
  const [strategyIds, setStrategyIds] = useState<string[]>([]);
  const [minRr, setMinRr] = useState(2);
  const [maxRiskPercent, setMaxRiskPercent] = useState(1);
  const [allowedSessions, setAllowedSessions] = useState<string[]>([...SESSIONS]);
  const [orderVolume, setOrderVolume] = useState(0.01);
  const [autoExecute, setAutoExecute] = useState(false);

  useEffect(() => {
    if (!open) return;
    void loadLab();
    void api.mt5Status().then((s) => setMt5Connected(Boolean(s.connected))).catch(() => setMt5Connected(false));
  }, [open, loadLab]);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setType("strategy");
    setName("");
    setScanIntervalSeconds(60);
    setAgents([...AGENTS]);
    setStrategyIds([]);
    setMinRr(2);
    setMaxRiskPercent(1);
    setAllowedSessions([...SESSIONS]);
    setOrderVolume(0.01);
    setAutoExecute(false);
  }, [open]);

  if (!open) return null;

  const steps =
    type === "alerts"
      ? [t("bots.wizard.step1"), t("bots.wizard.step2"), t("bots.wizard.step4")]
      : [
          t("bots.wizard.step1"),
          t("bots.wizard.step2"),
          t("bots.wizard.step3"),
          t("bots.wizard.step4"),
        ];

  const lastStep = steps.length - 1;
  const activeLabel = steps[step] ?? steps[0];

  const strategies = labItems.filter((r) => r.status === "active" || r.status === "validated");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (step < lastStep) {
      setStep((s) => s + 1);
      return;
    }
    setSubmitting(true);
    const body: BotInstanceCreatePayload = {
      name: name.trim(),
      type,
      scanIntervalSeconds: Math.max(15, scanIntervalSeconds),
      agents: type === "alerts" ? ["news_candle"] : agents.length ? agents : [...AGENTS],
      strategyIds: type === "strategy" || type === "quant" ? strategyIds : [],
      minRr,
      maxRiskPercent,
      allowedSessions,
      ...(type === "execution" ? { orderVolume, autoExecute } : {}),
    };
    const ok = await onSubmit(body);
    setSubmitting(false);
    if (ok) onClose();
  }

  function goBack() {
    if (step === 0) onClose();
    else setStep((s) => s - 1);
  }

  const stepIndex = type === "alerts" && step === 2 ? 3 : step;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-background/70 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="bot-wizard-title"
        className="fox-scroll max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 id="bot-wizard-title" className="font-semibold">{t("bots.wizard.title")}</h2>
            <p className="text-xs text-muted-foreground">{activeLabel}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg border border-border p-1.5" aria-label={t("bots.wizard.cancel")}>
            <X className="size-4" aria-hidden />
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 p-4">
          {error ? <p className="rounded-lg border border-sell/30 bg-sell/10 px-3 py-2 text-sm text-sell">{error}</p> : null}

          {stepIndex === 0 ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {BOT_TYPES.map((botType) => {
                const Icon = TYPE_ICONS[botType];
                const disabled = botType === "execution" && !mt5Connected;
                const selected = type === botType;
                return (
                  <button
                    key={botType}
                    type="button"
                    disabled={disabled}
                    onClick={() => !disabled && setType(botType)}
                    className={cn(
                      "rounded-xl border bg-background p-3 text-start transition",
                      TYPE_COLORS[botType],
                      selected && "ring-2 ring-foreground/20",
                      disabled && "cursor-not-allowed opacity-50"
                    )}
                  >
                    <Icon className={cn("mb-2 size-5", botType === "strategy" && "text-blue-400", botType === "quant" && "text-purple-400", botType === "alerts" && "text-amber-400", botType === "execution" && "text-red-400")} aria-hidden />
                    <p className="text-sm font-semibold">{t(`bots.type.${botType}` as MessageKey)}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{t(`bots.typeDesc.${botType}` as MessageKey)}</p>
                    {disabled ? (
                      <p className="mt-2 text-xs text-sell">
                        {t("bots.executionNeedsMt5")}{" "}
                        <Link href="/settings" className="underline" onClick={(e) => e.stopPropagation()}>
                          /settings
                        </Link>
                      </p>
                    ) : null}
                  </button>
                );
              })}
            </div>
          ) : null}

          {stepIndex === 1 ? (
            <div className="space-y-3">
              <label className="block text-xs text-muted-foreground">
                {t("bots.wizard.name")}
                <input
                  required
                  className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 text-sm"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label className="block text-xs text-muted-foreground">
                {t("bots.wizard.scanInterval")}
                <input
                  type="number"
                  min={15}
                  required
                  dir="ltr"
                  className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
                  value={scanIntervalSeconds}
                  onChange={(e) => setScanIntervalSeconds(Math.max(15, Number(e.target.value) || 15))}
                />
                <span className="mt-1 block text-[11px]">{t("bots.wizard.scanMin")}</span>
              </label>
            </div>
          ) : null}

          {stepIndex === 2 ? (
            <div className="space-y-4">
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">{t("bots.agents")}</p>
                <div className="flex flex-wrap gap-2">
                  {AGENTS.map((agent) => (
                    <label key={agent} className="flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs">
                      <input
                        type="checkbox"
                        checked={agents.includes(agent)}
                        onChange={() => setAgents((cur) => toggle(cur, agent))}
                      />
                      {t(`bot.agent.${agent}` as MessageKey)}
                    </label>
                  ))}
                </div>
              </div>
              {type === "strategy" || type === "quant" ? (
                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">{t("bots.strategies")}</p>
                  <div className="flex flex-wrap gap-2">
                    {strategies.length === 0 ? (
                      <p className="text-xs text-muted-foreground">{t("bots.empty")}</p>
                    ) : (
                      strategies.map((rule) => (
                        <label
                          key={rule.id}
                          className={cn(
                            "flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1 text-xs",
                            strategyIds.includes(rule.id) ? "border-buy/40 bg-buy/10 text-buy" : "border-border"
                          )}
                        >
                          <input
                            type="checkbox"
                            className="sr-only"
                            checked={strategyIds.includes(rule.id)}
                            onChange={() => setStrategyIds((cur) => toggle(cur, rule.id))}
                          />
                          {rule.name}
                        </label>
                      ))
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {stepIndex === 3 ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-muted-foreground">
                  {t("bots.minRr")}
                  <input
                    type="number"
                    min={0.5}
                    step={0.1}
                    dir="ltr"
                    className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
                    value={minRr}
                    onChange={(e) => setMinRr(Number(e.target.value) || 2)}
                  />
                </label>
                <label className="text-xs text-muted-foreground">
                  {t("bots.maxRisk")}
                  <input
                    type="number"
                    min={0.05}
                    step={0.05}
                    dir="ltr"
                    className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
                    value={maxRiskPercent}
                    onChange={(e) => setMaxRiskPercent(Number(e.target.value) || 1)}
                  />
                </label>
              </div>
              <div className="text-xs text-muted-foreground">
                {t("lab.sessions")}
                <div className="mt-1 flex flex-wrap gap-2">
                  {SESSIONS.map((session) => (
                    <label key={session} className="flex items-center gap-1 rounded-full border border-border px-2 py-1">
                      <input
                        type="checkbox"
                        checked={allowedSessions.includes(session)}
                        onChange={() => setAllowedSessions((cur) => toggle(cur, session))}
                      />
                      {t(sessionKey(session))}
                    </label>
                  ))}
                </div>
              </div>
              {type === "execution" ? (
                <>
                  <label className="block text-xs text-muted-foreground">
                    {t("bots.orderVolume")}
                    <input
                      type="number"
                      min={0.01}
                      step={0.01}
                      dir="ltr"
                      className="mt-1 w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
                      value={orderVolume}
                      onChange={(e) => setOrderVolume(Math.max(0.01, Number(e.target.value) || 0.01))}
                    />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={autoExecute} onChange={(e) => setAutoExecute(e.target.checked)} />
                    <span className="font-medium text-sell">{t("bots.autoExecute")}</span>
                  </label>
                  {autoExecute ? (
                    <p className="rounded-lg border border-sell/30 bg-sell/10 px-3 py-2 text-xs text-sell">
                      {t("bots.autoExecuteWarning")}
                    </p>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
            <button type="button" onClick={goBack} className="rounded-lg border border-border px-3 py-2 text-sm">
              {step === 0 ? t("bots.wizard.cancel") : t("bots.wizard.back")}
            </button>
            <button
              type="submit"
              disabled={submitting || (stepIndex === 1 && !name.trim())}
              className="rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-background disabled:opacity-50"
            >
              {step < lastStep ? t("bots.wizard.next") : t("bots.wizard.submit")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
