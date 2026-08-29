"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Send } from "lucide-react";
import { useSettings } from "@/stores/settings";
import { MODELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { LOCALE_IDS, useLocale, useT, type LocaleId, type MessageKey } from "@/i18n";

function Field({
  label,
  value,
  onChange,
  secret,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  secret?: boolean;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
      <div className="relative">
        <input
          type={secret && !show ? "password" : "text"}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-border bg-input px-3 py-2 pe-10 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        {secret && (
          <button type="button" onClick={() => setShow((s) => !s)} className="absolute end-2 top-1/2 -translate-y-1/2 text-muted-foreground">
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </label>
  );
}

export function SettingsPanel() {
  const form = useSettings((s) => s.form);
  const patchForm = useSettings((s) => s.patchForm);
  const load = useSettings((s) => s.load);
  const save = useSettings((s) => s.save);
  const validate = useSettings((s) => s.validate);
  const status = useSettings((s) => s.status);
  const pub = useSettings((s) => s.public);
  const locale = useLocale((s) => s.locale);
  const setLocale = useLocale((s) => s.setLocale);
  const t = useT();
  const [probe, setProbe] = useState<{ ready?: boolean; configured?: boolean; keyValid?: boolean; detail?: string }>({});

  useEffect(() => {
    void load().catch(() => undefined);
    void api
      .health()
      .then((h) =>
        setProbe({
          ready: h.anthropicReady ?? h.anthropic,
          configured: h.anthropicConfigured,
          keyValid: h.anthropicKeyValid,
          detail: h.anthropicDetail,
        })
      )
      .catch(() => undefined);
  }, [load]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-xl flex-1 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium tracking-tight">{t("settings.title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("settings.intro")}</p>

      <div className="mt-6 space-y-5">
        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">{t("settings.language")}</h2>
          <div className="flex gap-2">
            {LOCALE_IDS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setLocale(id as LocaleId)}
                className={cn(
                  "flex-1 rounded-lg border px-3 py-2 text-xs",
                  locale === id ? "border-foreground bg-muted" : "border-border text-muted-foreground"
                )}
              >
                {t(`locale.${id}` as MessageKey)}
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">{t("settings.anthropic")}</h2>
          <Field
            label="ANTHROPIC_API_KEY"
            secret
            value={form.anthropicApiKey}
            onChange={(anthropicApiKey) => patchForm({ anthropicApiKey })}
            placeholder={pub?.anthropicApiKeySet ? t("settings.secretPlaceholder") : "sk-ant-..."}
          />
          <button type="button" onClick={() => void validate("anthropic")} className="text-[12px] text-info hover:underline">
            {t("settings.verifyAnthropic")}
          </button>
          {probe.detail && (
            <p className={cn("text-[12px]", probe.ready ? "text-buy" : "text-sell")}>
              {probe.configured
                ? probe.ready
                  ? t("settings.keyReady")
                  : probe.keyValid
                    ? t("settings.keyRejected", { detail: probe.detail })
                    : probe.detail
                : t("settings.keyMissing")}
            </p>
          )}
          <label className="block space-y-1.5">
            <span className="text-[11px] font-medium text-muted-foreground">{t("settings.defaultModel")}</span>
            <select
              value={form.defaultClaudeModel}
              onChange={(e) => patchForm({ defaultClaudeModel: e.target.value })}
              className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm"
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">{t("settings.oanda")}</h2>
          <Field
            label="OANDA_API_TOKEN"
            secret
            value={form.oandaApiToken}
            onChange={(oandaApiToken) => patchForm({ oandaApiToken })}
            placeholder={pub?.oandaApiTokenSet ? t("settings.secretPlaceholder") : "OANDA v20 token"}
          />
          <Field
            label="OANDA_ACCOUNT_ID"
            value={form.oandaAccountId}
            onChange={(oandaAccountId) => patchForm({ oandaAccountId })}
            placeholder="001-..."
          />
          <div className="flex gap-2">
            {(["practice", "live"] as const).map((env) => (
              <button
                key={env}
                type="button"
                onClick={() => patchForm({ oandaEnvironment: env })}
                className={cn(
                  "flex-1 rounded-lg border px-3 py-2 text-xs capitalize",
                  form.oandaEnvironment === env ? "border-foreground bg-muted" : "border-border text-muted-foreground"
                )}
              >
                {env === "practice" ? t("settings.practice") : t("settings.live")}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => void validate("oanda")} className="text-[12px] text-info hover:underline">
            {t("settings.verifyOanda")}
          </button>
        </section>

        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">{t("settings.risk")}</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted-foreground">{t("settings.maxRisk")}</span>
              <input
                type="number"
                step="0.1"
                value={form.maxRiskPercent}
                onChange={(e) => patchForm({ maxRiskPercent: Number(e.target.value) })}
                className="w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted-foreground">{t("settings.minRr")}</span>
              <input
                type="number"
                step="0.1"
                value={form.minRiskReward}
                onChange={(e) => patchForm({ minRiskReward: Number(e.target.value) })}
                className="w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            {["london", "ny", "asian"].map((s) => {
              const on = form.allowedSessions.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() =>
                    patchForm({
                      allowedSessions: on ? form.allowedSessions.filter((x) => x !== s) : [...form.allowedSessions, s],
                    })
                  }
                  className={cn("rounded-full border px-3 py-1 text-xs capitalize", on ? "border-foreground bg-muted" : "border-border text-muted-foreground")}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">{t("settings.telegram")}</h2>
              <p className="text-xs text-muted-foreground">{t("settings.telegramHelp")}</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={form.enableTelegramNotifications}
              onClick={() => patchForm({ enableTelegramNotifications: !form.enableTelegramNotifications })}
              className={cn("relative h-6 w-11 shrink-0 rounded-full", form.enableTelegramNotifications ? "bg-foreground" : "bg-muted")}
            >
              <span className={cn("absolute top-0.5 size-5 rounded-full bg-background transition", form.enableTelegramNotifications ? "start-5" : "start-0.5")} />
            </button>
          </div>
          <Field
            label="TELEGRAM_BOT_TOKEN"
            secret
            value={form.telegramBotToken}
            onChange={(telegramBotToken) => patchForm({ telegramBotToken })}
            placeholder={pub?.telegramBotTokenSet ? t("settings.secretPlaceholder") : "123456:AA..."}
          />
          <Field
            label="TELEGRAM_CHAT_ID"
            value={form.telegramChatId}
            onChange={(telegramChatId) => patchForm({ telegramChatId })}
            placeholder={t("settings.telegramChatPlaceholder")}
          />
          <button type="button" onClick={() => void validate("telegram")} className="inline-flex items-center gap-1.5 text-[12px] text-info hover:underline">
            <Send className="h-3 w-3" />
            {t("settings.telegramTest")}
          </button>
        </section>

        {status && (
          <p
            className={cn(
              "rounded-lg px-3 py-2 text-xs",
              /fail|error|required|credit|too low|missing/i.test(status) ? "bg-sell/10 text-sell" : "bg-buy/10 text-buy"
            )}
          >
            {status}
          </p>
        )}

        <button type="button" onClick={() => void save()} className="w-full rounded-xl bg-foreground py-2.5 text-sm font-semibold text-background">
          {t("settings.save")}
        </button>
      </div>
    </div>
  );
}
