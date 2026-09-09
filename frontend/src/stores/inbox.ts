"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { DeskStatus, InboxCounts, InboxItem, InboxTab } from "@/lib/types";

const EMPTY_COUNTS: InboxCounts = { open: 0, inbox: 0, approvals: 0, alerts: 0 };

type InboxState = {
  items: InboxItem[];
  counts: InboxCounts;
  desk: DeskStatus | null;
  tab: InboxTab;
  loading: boolean;
  error: string;
  load: (tab?: InboxTab) => Promise<void>;
  setTab: (tab: InboxTab) => void;
  approve: (id: string) => Promise<void>;
  reject: (id: string, reason: string) => Promise<void>;
  ack: (id: string) => Promise<void>;
};

export const useInbox = create<InboxState>((set, get) => ({
  items: [],
  counts: EMPTY_COUNTS,
  desk: null,
  tab: "inbox",
  loading: false,
  error: "",
  setTab: (tab) => set({ tab }),
  load: async (tab) => {
    const next = tab || get().tab;
    set({ loading: true, error: "", tab: next });
    try {
      const snap = await api.inbox();
      const items = next === "inbox" ? snap.items : snap.items.filter((row) => row.tab === next);
      set({ items, counts: snap.counts, desk: snap.desk, loading: false });
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : "inbox failed" });
    }
  },
  approve: async (id) => {
    await api.approveInbox(id);
    await get().load();
  },
  reject: async (id, reason) => {
    await api.rejectInbox(id, reason);
    await get().load();
  },
  ack: async (id) => {
    await api.ackInbox(id);
    await get().load();
  },
}));
