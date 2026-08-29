"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Send } from "lucide-react";
import { useSettings } from "@/stores/settings";
import { MODELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

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

  useEffect(() => {
    void load().catch(() => undefined);
  }, [load]);

  return (
    <div className="fox-scroll mx-auto w-full max-w-xl flex-1 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium tracking-tight">الإعدادات</h1>
      <p className="mt-1 text-sm text-muted-foreground">المفاتيح تُشفَّر على الخادم. لا تُعدَّل مشاريع الاستضافة الأخرى من هنا.</p>

      <div className="mt-6 space-y-5">
        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">مفتاح Anthropic</h2>
          <Field
            label="ANTHROPIC_API_KEY"
            secret
            value={form.anthropicApiKey}
            onChange={(anthropicApiKey) => patchForm({ anthropicApiKey })}
            placeholder={pub?.anthropicApiKeySet ? "•••• محفوظ" : "sk-ant-..."}
          />
          <button type="button" onClick={() => void validate("anthropic")} className="text-[12px] text-info hover:underline">
            التحقق من المفتاح
          </button>
          <label className="block space-y-1.5">
            <span className="text-[11px] font-medium text-muted-foreground">نموذج كلود الافتراضي</span>
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
          <h2 className="text-sm font-semibold">OANDA</h2>
          <Field
            label="OANDA_API_TOKEN"
            secret
            value={form.oandaApiToken}
            onChange={(oandaApiToken) => patchForm({ oandaApiToken })}
            placeholder={pub?.oandaApiTokenSet ? "•••• محفوظ" : "OANDA v20 token"}
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
                {env === "practice" ? "تجريبي" : "حي"}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => void validate("oanda")} className="text-[12px] text-info hover:underline">
            التحقق من OANDA
          </button>
        </section>

        <section className="space-y-3 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">المخاطر</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted-foreground">أقصى مخاطرة %</span>
              <input
                type="number"
                step="0.1"
                value={form.maxRiskPercent}
                onChange={(e) => patchForm({ maxRiskPercent: Number(e.target.value) })}
                className="w-full rounded-lg border border-border bg-input px-3 py-2 font-mono text-sm"
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted-foreground">أدنى R:R</span>
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
              <h2 className="text-sm font-semibold">تنبيهات تيليجرام</h2>
              <p className="text-xs text-muted-foreground">إرسال الإعداد + صورة الشارت عند صدور توصية.</p>
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
            placeholder={pub?.telegramBotTokenSet ? "•••• محفوظ" : "123456:AA..."}
          />
          <Field
            label="TELEGRAM_CHAT_ID"
            value={form.telegramChatId}
            onChange={(telegramChatId) => patchForm({ telegramChatId })}
            placeholder="-100… أو @channel"
          />
          <button type="button" onClick={() => void validate("telegram")} className="inline-flex items-center gap-1.5 text-[12px] text-info hover:underline">
            <Send className="h-3 w-3" />
            إرسال رسالة تجريبية
          </button>
        </section>

        {status && (
          <p
            className={cn(
              "rounded-lg px-3 py-2 text-xs",
              /fail|error|required|فشل/i.test(status) ? "bg-sell/10 text-sell" : "bg-buy/10 text-buy"
            )}
          >
            {status}
          </p>
        )}

        <button type="button" onClick={() => void save()} className="w-full rounded-xl bg-foreground py-2.5 text-sm font-semibold text-background">
          حفظ الإعدادات المشفّرة
        </button>
      </div>
    </div>
  );
}
