"use client";

import { useEffect } from "react";
import { StrategyForm } from "@/components/strategy-lab/StrategyForm";
import { StrategyLibrary } from "@/components/strategy-lab/StrategyLibrary";
import { ValidationResult } from "@/components/strategy-lab/ValidationResult";
import { useStrategyLab } from "@/stores/strategyLab";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "library" as const, key: "lab.tab.library" as const },
  { id: "create" as const, key: "lab.tab.create" as const },
  { id: "proposed" as const, key: "lab.tab.proposed" as const },
  { id: "results" as const, key: "lab.tab.results" as const },
];

export default function StrategyLabRoute() {
  const t = useT();
  const load = useStrategyLab((s) => s.load);
  const items = useStrategyLab((s) => s.items);
  const tab = useStrategyLab((s) => s.tab);
  const setTab = useStrategyLab((s) => s.setTab);
  const error = useStrategyLab((s) => s.error);
  const lastValidation = useStrategyLab((s) => s.lastValidation);
  const history = useStrategyLab((s) => s.history);

  useEffect(() => {
    void load();
  }, [load]);

  const proposed = items.filter((r) => r.status === "draft" && r.source !== "builtin");
  const validated = items.filter((r) => r.validation_report_id || r.status === "validated" || r.status === "rejected");

  return (
    <div className="fox-scroll mx-auto w-full max-w-5xl flex-1 space-y-6 overflow-y-auto px-4 py-6">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight">{t("lab.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("lab.subtitle")}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm",
              tab === item.id ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            {t(item.key)}
          </button>
        ))}
      </div>
      {error ? <p className="text-sm text-sell">{error}</p> : null}
      {tab === "library" ? <StrategyLibrary items={items} /> : null}
      {tab === "create" ? <StrategyForm /> : null}
      {tab === "proposed" ? <StrategyLibrary items={proposed} /> : null}
      {tab === "results" ? (
        <div className="space-y-3">
          <ValidationResult result={lastValidation} />
          {history.slice(1).map((item, index) => (
            <ValidationResult key={`${item.strategy?.id || "r"}-${index}`} result={item} />
          ))}
          {!lastValidation && !validated.length ? <p className="text-sm text-muted-foreground">{t("lab.empty")}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
