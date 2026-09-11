"use client";

import { useEffect, useLayoutEffect, useRef } from "react";
import { AgentAvatar } from "./AgentAvatar";
import { ChatComposer } from "./ChatComposer";
import { ChatReasoning } from "./ChatReasoning";
import { ChatUsageMeter } from "./ChatUsageMeter";
import { RecommendationCard } from "./RecommendationCard";
import { StrategyProposalCard } from "@/components/strategy-lab/StrategyProposalCard";
import { StrategyJobCard } from "@/components/strategy-lab/StrategyJobCard";
import { ArtifactsWorkspace } from "./ArtifactsWorkspace";
import { DeskStatusCard } from "@/components/desk/DeskStatusCard";
import { useChat } from "@/stores/chat";
import { useInbox } from "@/stores/inbox";
import { useRecommendations } from "@/stores/recommendations";
import { useSessions } from "@/stores/sessions";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

export function ChatPanel() {
  const messages = useChat((s) => s.messages);
  const streaming = useChat((s) => s.streaming);
  const steps = useChat((s) => s.steps);
  const highlight = useChat((s) => s.highlight);
  const runUsage = useChat((s) => s.runUsage);
  const recs = useRecommendations((s) => s.items);
  const persistActive = useSessions((s) => s.persistActive);
  const desk = useInbox((s) => s.desk);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const isHero = messages.length === 0 && !streaming;
  const t = useT();

  useEffect(() => {
    persistActive(messages);
  }, [messages, persistActive]);

  useEffect(() => {
    if (isHero) return;
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming, isHero]);

  useLayoutEffect(() => {
    if (isHero) return;
    const dock = dockRef.current;
    const panel = panelRef.current;
    if (!dock || !panel) return;
    const apply = () => panel.style.setProperty("--composer-height", `${dock.offsetHeight}px`);
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(dock);
    return () => {
      ro.disconnect();
      panel.style.removeProperty("--composer-height");
    };
  }, [isHero]);

  const showInspector = streaming || steps.length > 0;

  return (
    <div className="flex h-full min-w-0 flex-1">
    <div ref={panelRef} className="chat-panel-shell h-full w-full min-w-0 flex-1 bg-transparent">
      <div
        ref={scrollerRef}
        data-hero={isHero || undefined}
        className={
          isHero
            ? "chat-scroll-region fox-scroll flex min-h-0 flex-1 flex-col overflow-y-auto p-3"
            : "chat-scroll-region fox-scroll min-h-0 flex-1 overflow-y-auto p-3"
        }
      >
        {isHero && (
          <div className="mx-auto flex min-h-0 w-full max-w-2xl flex-1 flex-col items-center justify-center gap-6 text-center">
            <AgentAvatar size={44} />
            <h2 className="font-serif text-balance px-4 text-2xl font-medium tracking-tight text-foreground sm:text-3xl">
              {t("chat.hero")}
            </h2>
            <div className="w-full">
              <ChatComposer hero />
            </div>
            <div className="w-full max-w-lg text-start">
              <DeskStatusCard desk={desk} compact />
            </div>
          </div>
        )}

        {!isHero && (
          <div className="flex flex-col space-y-3">
            {messages
              .filter((m) => m.role !== "system")
              .map((m) => (
                <div key={m.id} className="mx-auto w-full max-w-3xl">
                  {m.role === "user" ? (
                    <div className="ms-auto flex w-fit max-w-[min(85%,36rem)] flex-col items-end">
                      <div className="rounded-2xl bg-[var(--user-bubble)] px-3.5 py-2 text-sm leading-6 text-foreground">
                        <p className="whitespace-pre-wrap">{m.text}</p>
                      </div>
                    </div>
                  ) : (
                    <div
                      id={m.id}
                      className={cn(
                        "flex min-w-0 items-start gap-2.5 px-1 py-2 text-[0.9375rem] leading-7",
                        highlight === m.id && "rounded-xl ring-1 ring-warning"
                      )}
                    >
                      <AgentAvatar thinking={Boolean(m.streaming)} />
                      <div className="min-w-0 flex-1">
                        {m.streaming || (showInspector && m.id === messages.filter((x) => x.role === "assistant").at(-1)?.id) ? (
                          <ChatReasoning />
                        ) : null}
                        {m.images?.length ? (
                          <div className="mt-2 space-y-2">
                            {m.images.map((img) => (
                              <figure key={img.id} className="overflow-hidden rounded-xl border border-border/60 bg-card">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img src={img.src} alt={img.caption || ""} className="max-h-80 w-full object-contain" />
                              </figure>
                            ))}
                          </div>
                        ) : null}
                        {m.streaming && m.text ? (
                          <p className="whitespace-pre-wrap py-0.5 leading-7">
                            {m.text}
                            <span className="ms-0.5 inline-block h-3.5 w-[2px] animate-pulse bg-foreground/60 align-middle" />
                          </p>
                        ) : null}
                        {!m.streaming && m.recommendationId
                          ? recs
                              .filter((r) => r.id === m.recommendationId)
                              .map((r) => <RecommendationCard key={r.id} rec={r} />)
                          : null}
                        {!m.streaming && m.strategyProposal ? (
                          <StrategyProposalCard rule={m.strategyProposal} validation={m.strategyValidation} />
                        ) : null}
                        {!m.streaming && m.strategyExperiment ? <StrategyJobCard job={m.strategyExperiment} /> : null}
                        {!m.streaming && m.text ? (
                          m.recommendationId && m.text.length > 200 ? (
                            <details className="group mt-2 rounded-lg border border-border/50 bg-muted/20">
                              <summary className="flex min-h-9 cursor-pointer list-none items-center px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">
                                {t("chat.analysisDetails")}
                              </summary>
                              <p className="border-t border-border/40 px-3 py-2 whitespace-pre-wrap leading-relaxed">{m.text}</p>
                            </details>
                          ) : (
                            <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>
                          )
                        ) : null}
                        <ChatUsageMeter
                          usage={m.streaming ? runUsage || m.usage : m.usage}
                          live={Boolean(m.streaming && runUsage)}
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
          </div>
        )}
      </div>
      {!isHero && <div className="chat-composer-fade" aria-hidden />}
      {!isHero && (
        <div ref={dockRef} className="chat-composer-dock px-3 pb-3">
          <div className="mx-auto w-full max-w-3xl">
            <ChatComposer />
          </div>
        </div>
      )}
    </div>
    <ArtifactsWorkspace />
    </div>
  );
}
