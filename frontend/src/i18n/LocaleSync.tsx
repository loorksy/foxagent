"use client";

import { useEffect } from "react";
import { applyDocumentLocale, useLocale } from "./index";

export function LocaleSync() {
  const locale = useLocale((s) => s.locale);
  const hydrate = useLocale((s) => s.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    applyDocumentLocale(locale);
  }, [locale]);

  return null;
}
