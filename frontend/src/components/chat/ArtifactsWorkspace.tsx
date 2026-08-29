"use client";

import { useMemo, useRef, useState } from "react";
import { Check, Copy, Download, X } from "lucide-react";
import { useChat } from "@/stores/chat";
import { cn } from "@/lib/utils";
import { previewKind, toCsv, parseCsv } from "@/lib/antArtifact";
import { MarkdownPreview } from "@/components/artifacts/MarkdownPreview";
import { CodeEditor } from "@/components/artifacts/CodeEditor";
import { CsvSheet } from "@/components/artifacts/CsvSheet";
import { MermaidView } from "@/components/artifacts/MermaidView";
import { useT, type MessageKey } from "@/i18n";

const TAB_KEYS: { id: ReturnType<typeof previewKind>; label: MessageKey }[] = [
  { id: "markdown", label: "artifacts.tabMarkdown" },
  { id: "code", label: "artifacts.tabCode" },
  { id: "csv", label: "artifacts.tabSheet" },
  { id: "mermaid", label: "artifacts.tabDiagram" },
];

export function ArtifactsWorkspace() {
  const artifacts = useChat((s) => s.artifacts);
  const open = useChat((s) => s.artifactsOpen);
  const width = useChat((s) => s.artifactsWidth);
  const activeId = useChat((s) => s.activeArtifactId);
  const highlight = useChat((s) => s.highlight);
  const setOpen = useChat((s) => s.setArtifactsOpen);
  const setWidth = useChat((s) => s.setArtifactsWidth);
  const setActive = useChat((s) => s.setActiveArtifact);
  const endArtifact = useChat((s) => s.endArtifact);
  const [copied, setCopied] = useState(false);
  const [tabOverride, setTabOverride] = useState<string | null>(null);
  const drag = useRef<{ startX: number; startW: number } | null>(null);
  const t = useT();

  const active = useMemo(
    () =>
      artifacts.find((a) => a.id === (highlight && artifacts.some((x) => x.id === highlight) ? highlight : activeId)) ||
      artifacts[artifacts.length - 1],
    [activeId, artifacts, highlight]
  );

  const autoKind = previewKind(active?.type || "", active?.language);
  const kind = (tabOverride as typeof autoKind) || autoKind;

  if (!open) return null;

  function exportName() {
    const base = (active?.title || "artifact").replace(/\s+/g, "-");
    if (kind === "csv") return `${base}.csv`;
    if (kind === "mermaid") return `${base}.mmd`;
    if (kind === "code") return `${base}.${active?.language || "txt"}`;
    if (kind === "svg") return `${base}.svg`;
    return `${base}.md`;
  }

  function exportBody() {
    if (kind === "csv") return toCsv(parseCsv(active?.body || ""));
    return active?.body || "";
  }

  const panel = (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex h-12 items-center justify-between border-b border-border px-3">
        <p className="text-sm font-medium">{t("artifacts.title")}</p>
        <button type="button" className="rounded-md p-1 text-muted-foreground hover:bg-muted" onClick={() => setOpen(false)} aria-label={t("artifacts.close")}>
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1">
        <ul className="fox-scroll w-36 shrink-0 overflow-y-auto border-e border-border p-2">
          {artifacts.length === 0 && <li className="px-1 py-2 text-[11px] text-muted-foreground">{t("artifacts.empty")}</li>}
          {artifacts.map((art) => (
            <li key={art.id}>
              <button
                type="button"
                onClick={() => {
                  setTabOverride(null);
                  setActive(art.id);
                }}
                className={cn(
                  "mb-1 w-full rounded-md px-2 py-1.5 text-start text-[11px]",
                  (active?.id === art.id || highlight === art.id) && "bg-muted text-foreground",
                  highlight === art.id && "ring-1 ring-warning"
                )}
              >
                <span className="block truncate font-medium">{art.title}</span>
                <span className="block truncate text-muted-foreground">{art.language || art.type}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="flex min-w-0 flex-1 flex-col">
          {active ? (
            <>
              <div className="flex flex-wrap items-center gap-1 border-b border-border px-3 py-2">
                {TAB_KEYS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setTabOverride(tab.id)}
                    className={cn(
                      "rounded-md px-2 py-1 text-[11px]",
                      kind === tab.id ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {t(tab.label)}
                  </button>
                ))}
                <div className="ms-auto flex items-center gap-1">
                  <button
                    type="button"
                    className="rounded-md border border-border px-2 py-1 text-[11px]"
                    onClick={() => {
                      void navigator.clipboard.writeText(exportBody());
                      setCopied(true);
                      window.setTimeout(() => setCopied(false), 1200);
                    }}
                  >
                    {copied ? <Check className="inline h-3.5 w-3.5" /> : <Copy className="inline h-3.5 w-3.5" />}
                    <span className="ms-1">{copied ? t("artifacts.copied") : t("artifacts.copy")}</span>
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-border px-2 py-1 text-[11px]"
                    onClick={() => {
                      const blob = new Blob([exportBody()], { type: "text/plain" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = exportName();
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <Download className="me-1 inline h-3.5 w-3.5" />
                    {t("artifacts.export")}
                  </button>
                </div>
              </div>
              <div className="fox-scroll min-h-0 flex-1 overflow-auto p-3">
                {kind === "markdown" && <MarkdownPreview body={active.body || ""} />}
                {kind === "plain" && <pre className="whitespace-pre-wrap font-mono text-[12px] leading-6">{active.body}</pre>}
                {kind === "code" && (
                  <CodeEditor
                    body={active.body || ""}
                    language={active.language || "text"}
                    onLanguage={(language) => endArtifact({ ...active, language })}
                    onChange={(body) => endArtifact({ ...active, body })}
                  />
                )}
                {kind === "csv" && <CsvSheet body={active.body || ""} onChange={(body) => endArtifact({ ...active, body })} />}
                {kind === "mermaid" && <MermaidView body={active.body || ""} />}
                {kind === "svg" && <div className="art-mermaid" dangerouslySetInnerHTML={{ __html: active.body || "" }} />}
              </div>
            </>
          ) : (
            <p className="p-3 text-sm text-muted-foreground">{t("artifacts.empty")}</p>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="relative hidden h-full shrink-0 border-s border-border bg-card xl:flex" style={{ width }}>
        <button
          type="button"
          aria-label="Resize artifacts"
          className="absolute inset-y-0 start-0 z-10 w-1.5 cursor-col-resize hover:bg-foreground/20"
          onMouseDown={(e) => {
            drag.current = { startX: e.clientX, startW: width };
            const move = (ev: MouseEvent) => {
              if (!drag.current) return;
              const dir = document.documentElement.dir === "rtl" ? -1 : 1;
              setWidth(drag.current.startW - dir * (ev.clientX - drag.current.startX));
            };
            const up = () => {
              drag.current = null;
              window.removeEventListener("mousemove", move);
              window.removeEventListener("mouseup", up);
            };
            window.addEventListener("mousemove", move);
            window.addEventListener("mouseup", up);
          }}
        />
        {panel}
      </aside>
      <div className="xl:hidden">
        <button type="button" className="absolute inset-0 z-30 bg-black/50" aria-label={t("artifacts.close")} onClick={() => setOpen(false)} />
        <div className="absolute inset-x-0 bottom-0 z-40 flex h-[78dvh] flex-col overflow-hidden rounded-t-2xl border-t border-border bg-background shadow-xl">
          {panel}
        </div>
      </div>
    </>
  );
}
