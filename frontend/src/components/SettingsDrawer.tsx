"use client";

import { useEffect, useState } from "react";
import { useSettings } from "@/stores/settings";
import { MODELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Eye, EyeOff, X } from "lucide-react";

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
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <div className="relative">
        <input
          type={secret && !show ? "password" : "text"}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 pr-10 font-mono text-sm text-slate-100 outline-none focus:border-gold-500/40"
        />
        {secret && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500"
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </label>
  );
}

export function SettingsDrawer() {
  const open = useSettings((s) => s.open);
  const setOpen = useSettings((s) => s.setOpen);
  const form = useSettings((s) => s.form);
  const patchForm = useSettings((s) => s.patchForm);
  const load = useSettings((s) => s.load);
  const save = useSettings((s) => s.save);
  const validate = useSettings((s) => s.validate);
  const status = useSettings((s) => s.status);
  const pub = useSettings((s) => s.public);

  useEffect(() => {
    if (open) void load().catch(() => undefined);
  }, [open, load]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm">
      <aside className="glass h-full w-full max-w-md overflow-y-auto p-5">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">قسم الإعدادات</p>
            <h2 className="text-lg font-semibold">System Configuration</h2>
            <p className="text-xs text-slate-500">Secrets are encrypted at rest on the backend.</p>
          </div>
          <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1 text-slate-400 hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <Field
            label="ANTHROPIC_API_KEY"
            secret
            value={form.anthropicApiKey}
            onChange={(anthropicApiKey) => patchForm({ anthropicApiKey })}
            placeholder={pub?.anthropicApiKeySet ? "•••• key stored" : "sk-ant-..."}
          />
          <button
            type="button"
            onClick={() => void validate("anthropic")}
            className="text-[11px] text-cyan-300 hover:underline"
          >
            Validate Anthropic key
          </button>

          <Field
            label="OANDA_API_TOKEN"
            secret
            value={form.oandaApiToken}
            onChange={(oandaApiToken) => patchForm({ oandaApiToken })}
            placeholder={pub?.oandaApiTokenSet ? "•••• token stored" : "OANDA v20 token"}
          />
          <Field
            label="OANDA_ACCOUNT_ID"
            value={form.oandaAccountId}
            onChange={(oandaAccountId) => patchForm({ oandaAccountId })}
            placeholder="001-..."
          />

          <div className="space-y-1.5">
            <span className="text-[11px] uppercase tracking-wider text-slate-500">OANDA_ENVIRONMENT</span>
            <div className="flex gap-2">
              {(["practice", "live"] as const).map((env) => (
                <button
                  key={env}
                  type="button"
                  onClick={() => patchForm({ oandaEnvironment: env })}
                  className={cn(
                    "flex-1 rounded-lg border px-3 py-2 text-xs capitalize",
                    form.oandaEnvironment === env
                      ? "border-gold-500/40 bg-gold-500/15 text-gold-400"
                      : "border-white/10 text-slate-400"
                  )}
                >
                  {env === "practice" ? "Practice / Sandbox" : "Live"}
                </button>
              ))}
            </div>
          </div>
          <button type="button" onClick={() => void validate("oanda")} className="text-[11px] text-cyan-300 hover:underline">
            Validate OANDA credentials
          </button>

          <label className="block space-y-1.5">
            <span className="text-[11px] uppercase tracking-wider text-slate-500">DEFAULT_CLAUDE_MODEL</span>
            <select
              value={form.defaultClaudeModel}
              onChange={(e) => patchForm({ defaultClaudeModel: e.target.value })}
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm"
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5">
              <span className="text-[11px] uppercase tracking-wider text-slate-500">Max risk %</span>
              <input
                type="number"
                step="0.1"
                value={form.maxRiskPercent}
                onChange={(e) => patchForm({ maxRiskPercent: Number(e.target.value) })}
                className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-sm"
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] uppercase tracking-wider text-slate-500">Min R:R</span>
              <input
                type="number"
                step="0.1"
                value={form.minRiskReward}
                onChange={(e) => patchForm({ minRiskReward: Number(e.target.value) })}
                className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-sm"
              />
            </label>
          </div>

          <div>
            <span className="text-[11px] uppercase tracking-wider text-slate-500">Allowed sessions</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {["london", "ny", "asian"].map((s) => {
                const on = form.allowedSessions.includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() =>
                      patchForm({
                        allowedSessions: on
                          ? form.allowedSessions.filter((x) => x !== s)
                          : [...form.allowedSessions, s],
                      })
                    }
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs capitalize",
                      on ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-200" : "border-white/10 text-slate-500"
                    )}
                  >
                    {s}
                  </button>
                );
              })}
            </div>
          </div>

          {status && <p className="text-xs text-cyan-200">{status}</p>}

          <button
            type="button"
            onClick={() => void save()}
            className="w-full rounded-xl bg-gold-500 py-2.5 text-sm font-semibold text-ink-950"
          >
            Save encrypted settings
          </button>
        </div>
      </aside>
    </div>
  );
}
