"use client";

import { create } from "zustand";
import { api } from "@/lib/api";
import type { EconomicEvent } from "@/lib/types";

type CalendarState = {
  events: EconomicEvent[];
  source: string;
  loading: boolean;
  load: (hoursAhead?: number) => Promise<void>;
};

export const useCalendar = create<CalendarState>((set) => ({
  events: [],
  source: "",
  loading: false,
  load: async (hoursAhead = 48) => {
    set({ loading: true });
    try {
      const data = await api.economicCalendar(hoursAhead, "medium");
      set({ events: data.events || [], source: data.source, loading: false });
    } catch {
      set({ events: [], loading: false });
    }
  },
}));
