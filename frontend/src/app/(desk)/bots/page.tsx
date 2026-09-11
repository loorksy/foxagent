"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { BotCreateWizard } from "@/components/bot/BotCreateWizard";
import { BotInstanceCard } from "@/components/bot/BotInstanceCard";
import { useBotInstances } from "@/stores/botInstances";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

const SCAN_DESKS = [
  { href: "/bots/structure", labelKey: "bots.structure" as const },
  { href: "/bots/patterns", labelKey: "bots.patterns" as const },
  { href: "/bots/news", labelKey: "bots.news" as const },
];

export default function BotsRoom() {
  const t = useT();
  const instances = useBotInstances((s) => s.instances);
  const paused = useBotInstances((s) => s.paused);
  const loading = useBotInstances((s) => s.loading);
  const error = useBotInstances((s) => s.error);
  const load = useBotInstances((s) => s.load);
  const create = useBotInstances((s) => s.create);
  const patch = useBotInstances((s) => s.patch);
  const remove = useBotInstances((s) => s.remove);
  const start = useBotInstances((s) => s.start);
  const stop = useBotInstances((s) => s.stop);

  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardError, setWizardError] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(id);
  }, [load]);

  async function handleCreate(body: Parameters<typeof create>[0]) {
    setWizardError("");
    const inst = await create(body);
    if (!inst) {
      setWizardError(useBotInstances.getState().error);
      return false;
    }
    return true;
  }

  async function withAction(id: string, fn: () => Promise<void>) {
    setActionId(id);
    await fn();
    setActionId(null);
  }

  return (
    <div className="fox-scroll mx-auto w-full max-w-5xl flex-1 space-y-6 overflow-y-auto px-4 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl font-medium tracking-tight">{t("bots.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("bots.subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setWizardError("");
            setWizardOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-xl bg-foreground px-4 py-2.5 text-sm font-semibold text-background"
        >
          <Plus className="size-4" aria-hidden />
          {t("bots.create")}
        </button>
      </div>

      {paused ? (
        <div className="rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          {t("bots.pausedBanner")}
        </div>
      ) : null}

      {error && !wizardOpen ? <p className="text-sm text-sell">{error}</p> : null}

      <section>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground">{t("bots.fleet")}</h2>
        {loading && instances.length === 0 ? (
          <p className="text-sm text-muted-foreground">…</p>
        ) : instances.length === 0 ? (
          <p className="rounded-xl border border-border bg-card p-6 text-center text-sm text-muted-foreground">
            {t("bots.empty")}
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {instances.map((bot) => (
              <BotInstanceCard
                key={bot.id}
                bot={bot}
                busy={actionId === bot.id}
                onToggleEnabled={(enabled) => void withAction(bot.id, () => patch(bot.id, { enabled }))}
                onStart={() => void withAction(bot.id, () => start(bot.id))}
                onStop={() => void withAction(bot.id, () => stop(bot.id))}
                onDelete={() => void withAction(bot.id, () => remove(bot.id))}
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground">{t("bots.scanDesks")}</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {SCAN_DESKS.map((desk) => (
            <Link
              key={desk.href}
              href={desk.href}
              className={cn("rounded-xl border border-border bg-card p-4 transition hover:border-foreground/20")}
            >
              <p className="font-semibold">{t(desk.labelKey)}</p>
            </Link>
          ))}
        </div>
      </section>

      <BotCreateWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onSubmit={handleCreate}
        error={wizardError}
      />
    </div>
  );
}
