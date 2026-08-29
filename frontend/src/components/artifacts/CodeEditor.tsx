"use client";

import { useMemo } from "react";
import { CODE_LANGUAGES } from "@/lib/antArtifact";
import { highlightCode } from "@/lib/highlight";
import { useT } from "@/i18n";

export function CodeEditor({
  body,
  language,
  onLanguage,
  onChange,
}: {
  body: string;
  language: string;
  onLanguage: (language: string) => void;
  onChange?: (body: string) => void;
}) {
  const t = useT();
  const lang = language || "text";
  const html = useMemo(() => highlightCode(body || "", lang), [body, lang]);
  const lines = (body || "").split("\n");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <label className="mb-2 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>{t("artifacts.language")}</span>
        <select
          value={CODE_LANGUAGES.includes(lang) ? lang : "text"}
          onChange={(e) => onLanguage(e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 font-mono text-[11px] text-foreground"
        >
          {!CODE_LANGUAGES.includes(lang) && <option value={lang}>{lang}</option>}
          {CODE_LANGUAGES.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-[#0b0b0b]">
        <div className="fox-scroll absolute inset-0 overflow-auto">
          <div className="flex min-w-max font-mono text-[12px] leading-6">
            <pre className="select-none border-e border-border/60 px-2 py-2 text-end text-muted-foreground/70">
              {lines.map((_, i) => `${i + 1}\n`).join("")}
            </pre>
            <div className="relative min-w-[40rem] flex-1">
              <pre className="pointer-events-none absolute inset-0 whitespace-pre px-3 py-2" dangerouslySetInnerHTML={{ __html: html || " " }} />
              <textarea
                value={body}
                spellCheck={false}
                onChange={(e) => onChange?.(e.target.value)}
                className="relative z-10 h-full min-h-[16rem] w-full resize-none bg-transparent px-3 py-2 text-transparent caret-foreground outline-none"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
