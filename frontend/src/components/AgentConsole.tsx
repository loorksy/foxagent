"use client";

import { useEffect, useRef } from "react";
import { ThoughtStepper } from "./ThoughtStepper";
import { MessageBubble } from "./MessageBubble";
import { Omnibar } from "./Omnibar";
import { ViewSwitcher } from "./ViewSwitcher";
import { useChat } from "@/stores/chat";
import { useWorkspace } from "@/stores/workspace";

export function AgentConsole() {
  const messages = useChat((s) => s.messages);
  const viewMode = useWorkspace((s) => s.viewMode);
  const setViewMode = useWorkspace((s) => s.setViewMode);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <section className="glass flex h-full min-h-0 flex-col overflow-hidden rounded-2xl">
      <header className="flex items-center justify-between gap-2 border-b border-white/5 px-3 py-2.5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">قسم Agent</p>
          <h2 className="text-sm font-semibold text-slate-100">Claude Agent Console</h2>
        </div>
        <ViewSwitcher value={viewMode} onChange={setViewMode} />
      </header>
      <div className="border-b border-white/5 px-3 py-3">
        <ThoughtStepper />
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-white/5 px-3 py-3">
        <Omnibar />
      </div>
    </section>
  );
}
