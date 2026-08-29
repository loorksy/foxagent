"use client";

import { create } from "zustand";
import type { SettingsPayload, SettingsPublic } from "@/lib/types";
import { api } from "@/lib/api";
import { MODELS } from "@/lib/constants";

type SettingsState = {
  public: SettingsPublic | null;
  form: SettingsPayload;
  status: string;
  patchForm: (patch: Partial<SettingsPayload>) => void;
  load: () => Promise<void>;
  save: () => Promise<void>;
  validate: (target: "anthropic" | "oanda" | "telegram") => Promise<void>;
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
  telegramBotToken: "",
  telegramChatId: "",
  enableTelegramNotifications: false,
};

export const useSettings = create<SettingsState>((set, get) => ({
  public: null,
  form: emptyForm,
  status: "",
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
        telegramChatId: pub.telegramChatId || "",
        enableTelegramNotifications: Boolean(pub.enableTelegramNotifications),
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
      telegramBotToken: form.telegramBotToken,
      telegramChatId: form.telegramChatId,
    });
    set({ status: res.detail });
  },
}));
