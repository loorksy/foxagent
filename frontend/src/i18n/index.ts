"use client";

import { useMemo } from "react";
import { create } from "zustand";
import { ar, type MessageKey } from "./messages/ar";
import { en } from "./messages/en";

export type { MessageKey };

export type LocaleId = "ar" | "en";
export type TextDir = "rtl" | "ltr";

type LocaleEntry = {
  id: LocaleId;
  dir: TextDir;
  messages: Record<MessageKey, string>;
};

/**
 * Language map. Add a file under ./messages and register it here to ship another locale.
 */
export const LOCALES: Record<LocaleId, LocaleEntry> = {
  ar: { id: "ar", dir: "rtl", messages: ar },
  en: { id: "en", dir: "ltr", messages: en },
};

export const LOCALE_IDS = Object.keys(LOCALES) as LocaleId[];
export const DEFAULT_LOCALE: LocaleId = "ar";
const STORAGE_KEY = "foxagent_locale";

type LocaleState = {
  locale: LocaleId;
  hydrate: () => void;
  setLocale: (locale: LocaleId) => void;
};

function isLocaleId(value: string | null): value is LocaleId {
  return Boolean(value && value in LOCALES);
}

export const useLocale = create<LocaleState>((set) => ({
  locale: DEFAULT_LOCALE,
  hydrate: () => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocaleId(stored)) set({ locale: stored });
  },
  setLocale: (locale) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, locale);
    }
    set({ locale });
  },
}));

function interpolate(template: string, vars?: Record<string, string | number>) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? ""));
}

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const locale = useLocale.getState().locale;
  const table = LOCALES[locale]?.messages ?? LOCALES[DEFAULT_LOCALE].messages;
  const fallback = LOCALES.en.messages;
  return interpolate(table[key] ?? fallback[key] ?? key, vars);
}

export function useT() {
  const locale = useLocale((s) => s.locale);
  return useMemo(() => {
    void locale;
    return (key: MessageKey, vars?: Record<string, string | number>) => t(key, vars);
  }, [locale]);
}

export function useDir(): TextDir {
  const locale = useLocale((s) => s.locale);
  return LOCALES[locale].dir;
}

export function applyDocumentLocale(locale: LocaleId) {
  if (typeof document === "undefined") return;
  const entry = LOCALES[locale];
  document.documentElement.lang = entry.id;
  document.documentElement.dir = entry.dir;
}

export function recStatusKey(status: string): MessageKey {
  const key = `rec.status.${status}` as MessageKey;
  return key in ar ? key : "rec.status.PENDING";
}
