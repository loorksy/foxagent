"use client";

import { EconomicCalendar } from "@/components/calendar/EconomicCalendar";
import { useT } from "@/i18n";

export default function CalendarRoute() {
  const t = useT();
  return (
    <div className="fox-scroll mx-auto w-full max-w-4xl flex-1 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium tracking-tight">{t("calendar.title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("calendar.subtitle")}</p>
      <div className="mt-6">
        <EconomicCalendar />
      </div>
    </div>
  );
}
