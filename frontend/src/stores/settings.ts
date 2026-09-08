"use client";

import { create } from "zustand";
import type { SettingsPayload, SettingsPublic } from "@/lib/types";
import { api } from "@/lib/api";
import { MODELS } from "@/lib/constants";
import { t } from "@/i18n";

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
  botEnabled: false,
  botScanInterval: 60,
  botAgents: ["multi_strategy", "pattern_notes", "news_candle"],
  botActiveStrategies: [
    "gold_liquidity_sniper",
    "gold_breakout",
    "gold_trend_follow",
    "gold_reversal",
    "gold_scalp",
  ],
  botMaxRiskPercent: 1,
  botMinRr: 2,
  botAllowedSessions: ["london", "ny", "asian"],
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
        botEnabled: Boolean(pub.botEnabled),
        botScanInterval: pub.botScanInterval || 60,
        botAgents: pub.botAgents || s.form.botAgents,
        botActiveStrategies: pub.botActiveStrategies || s.form.botActiveStrategies,
        botMaxRiskPercent: pub.botMaxRiskPercent ?? 1,
        botMinRr: pub.botMinRr ?? 2,
        botAllowedSessions: pub.botAllowedSessions || s.form.botAllowedSessions,
      },
    }));
  },
  save: async () => {
    const pub = await api.saveSettings(get().form);
    set({ public: pub, status: t("settings.saved") });
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
