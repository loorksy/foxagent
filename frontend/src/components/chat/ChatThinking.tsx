"use client";

import { ChevronDown, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useChat } from "@/stores/chat";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

export function ChatThinking() {
  const thoughts = useChat((s) => s.thoughts);
  const tools = useChat((s) => s.tools);
  const debate = useChat((s) => s.debate);
  const recalls = useChat((s) => s.recalls);
  const streaming = useChat((s) => s.streaming);
  const [open, setOpen] = useState(true);
  const t = useT();

  const latest = useMemo(() => {
    const last = [...thoughts].reverse().find((item) => item.text.trim());
    return last ? last.text.trim().slice(-180) : "";
  }, [thoughts]);
  const agent = thoughts[thoughts.length - 1]?.agent || "";

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-9 w-full items-start gap-1.5 text-start text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        {streaming ? <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" /> : null}
        <span className="min-w-0 flex-1 whitespace-pre-wrap font-mono text-[12px] leading-5">
          {latest || (agent ? agent : t("run.live"))}
        </span>
        <ChevronDown className={cn("mt-0.5 h-3.5 w-3.5 shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 space-y-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
          {recalls.length > 0 && (
            <section>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("run.memory")}</p>
              {recalls.map((recall, i) => (
                <pre key={i} className="whitespace-pre-wrap font-mono text-[11px] text-warning">
                  {recall.text || (recall.lessons || []).join("\n")}
                </pre>
              ))}
            </section>
          )}
          {thoughts.length > 0 && (
            <section>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("run.thoughts")}</p>
              <div className="fox-scroll max-h-48 space-y-2 overflow-y-auto">
                {thoughts.map((item, i) => (
                  <p key={`${item.agent}-${i}`} className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-foreground/90">
                    <span className="text-muted-foreground">{item.agent}: </span>
                    {item.text.slice(-2000)}
                  </p>
                ))}
              </div>
            </section>
          )}
          {tools.length > 0 && (
            <section>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("run.tools")}</p>
              <ul className="space-y-1.5">
                {tools.map((tool) => (
                  <li key={tool.id || tool.name} className="rounded-md border border-border/40 bg-background/60 p-2 font-mono text-[11px]">
                    <p className="text-foreground">
                      {tool.agent} · {tool.name}
                    </p>
                    {tool.input != null && (
                      <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-muted-foreground">
                        {JSON.stringify(tool.input, null, 2).slice(0, 800)}
                      </pre>
                    )}
                    {tool.output != null && (
                      <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-muted-foreground">
                        {JSON.stringify(tool.output, null, 2).slice(0, 800)}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {debate.length > 0 && (
            <section>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("run.debate")}</p>
              <div className="space-y-2">
                {debate.map((line, i) => (
                  <article key={i} className="rounded-md border border-border/40 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {line.role === "bull" ? t("run.bull") : line.role === "bear" ? t("run.bear") : line.agent}
                    </p>
                    <p className="whitespace-pre-wrap text-[12px] leading-5">{line.text}</p>
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
