"use client";

import { create } from "zustand";
import type { SettingsPayload, SettingsPublic } from "@/lib/types";
import { api } from "@/lib/api";
import { MODELS } from "@/lib/constants";

type SettingsState = {
  open: boolean;
  public: SettingsPublic | null;
  form: SettingsPayload;
  status: string;
  setOpen: (open: boolean) => void;
  patchForm: (patch: Partial<SettingsPayload>) => void;
  load: () => Promise<void>;
  save: () => Promise<void>;
  validate: (target: "anthropic" | "oanda") => Promise<void>;
};

const emptyForm: SettingsPayload = {
  anthropicApiKey: "",
  oandaApiToken: "",
  oandaAccountId: "",
  oandaEnvironment: "practice",
  defaultClaudeModel: MODELS[0].id,
  maxRiskPercent: 1,
  minRiskReward: 2,
  allowedSessions: ["london", "ny", "asian"],
};

export const useSettings = create<SettingsState>((set, get) => ({
  open: false,
  public: null,
  form: emptyForm,
  status: "",
  setOpen: (open) => set({ open }),
  patchForm: (patch) => set((s) => ({ form: { ...s.form, ...patch } })),
  load: async () => {
    const pub = await api.settings();
    set((s) => ({
      public: pub,
      form: {
        ...s.form,
        oandaAccountId: pub.oandaAccountId,
        oandaEnvironment: (pub.oandaEnvironment as "practice" | "live") || "practice",
        defaultClaudeModel: pub.defaultClaudeModel,
        maxRiskPercent: pub.maxRiskPercent,
        minRiskReward: pub.minRiskReward,
        allowedSessions: pub.allowedSessions,
      },
    }));
  },
  save: async () => {
    const pub = await api.saveSettings(get().form);
    set({ public: pub, status: "Saved to encrypted store" });
  },
  validate: async (target) => {
    const form = get().form;
    const res = await api.validateSettings({
      target,
      anthropicApiKey: form.anthropicApiKey,
      oandaApiToken: form.oandaApiToken,
      oandaAccountId: form.oandaAccountId,
      oandaEnvironment: form.oandaEnvironment,
    });
    set({ status: res.detail });
  },
}));
