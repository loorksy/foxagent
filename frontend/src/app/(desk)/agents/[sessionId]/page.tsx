"use client";

import { useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { SettingsPanel } from "@/components/settings/SettingsPanel";
import { useSessions } from "@/stores/sessions";
import { useChat } from "@/stores/chat";
import { useWorkspace } from "@/stores/workspace";

export default function AgentSessionPage() {
  const params = useParams<{ sessionId: string }>();
  const search = useSearchParams();
  const sessionId = params.sessionId;
  const openSession = useSessions((s) => s.openSession);
  const setActiveId = useSessions((s) => s.setActiveId);
  const app = search.get("app");

  useEffect(() => {
    if (!sessionId || sessionId === "new") return;
    setActiveId(sessionId);
    void openSession(sessionId);
  }, [openSession, sessionId, setActiveId]);

  useEffect(() => {
    if (search.get("app") === "artifacts") useChat.getState().setArtifactsOpen(true);
    if (search.get("app") === "chart") useWorkspace.getState().setChartOpen(true);
    useChat.getState().setHighlight(search.get("highlight"));
  }, [search]);

  if (app === "environment") {
    return <SettingsPanel />;
  }

  return <ChatPanel />;
}
