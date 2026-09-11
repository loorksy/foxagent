"use client";

import { useEffect } from "react";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { useChat } from "@/stores/chat";
import { useSessions } from "@/stores/sessions";

/**
 * New-chat landing. No session row is created here — the backend creates the
 * session lazily when the first message is sent, and the URL is adopted then.
 */
export default function AgentsIndexPage() {
  useEffect(() => {
    useSessions.getState().setActiveId(null);
    useChat.getState().clearChat();
  }, []);

  return <ChatPanel />;
}
