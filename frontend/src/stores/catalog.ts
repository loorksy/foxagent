"use client";

import { create } from "zustand";
import { DEFAULT_INSTRUMENTS, MODELS } from "@/lib/constants";
import { api } from "@/lib/api";
import type { Instrument, ModelOption } from "@/lib/types";

type CatalogState = {
  models: ModelOption[];
  instruments: Instrument[];
  loaded: boolean;
  load: () => Promise<void>;
};

export const useCatalog = create<CatalogState>((set, get) => ({
  models: MODELS,
  instruments: DEFAULT_INSTRUMENTS,
  loaded: false,
  load: async () => {
    if (get().loaded) return;
    try {
      const [modelsRes, instrumentsRes] = await Promise.all([api.models(), api.instruments()]);
      set({
        models: modelsRes.models?.length ? modelsRes.models : MODELS,
        instruments: instrumentsRes.instruments?.length ? instrumentsRes.instruments : DEFAULT_INSTRUMENTS,
        loaded: true,
      });
    } catch {
      set({ loaded: true });
    }
  },
}));
