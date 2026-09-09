"use client";

import { BotDesk } from "@/components/bot/BotDesk";
import { useT } from "@/i18n";

export default function StructureBotPage() {
  const t = useT();
  return (
    <div className="fox-scroll mx-auto w-full max-w-5xl flex-1 space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="font-serif text-2xl font-medium">{t("bots.structure")}</h1>
      <p className="text-sm text-muted-foreground">{t("bots.structureHelp")}</p>
      <BotDesk />
    </div>
  );
}
