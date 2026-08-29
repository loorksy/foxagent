"use client";

import { useMemo, useRef, useState } from "react";
import { Check, Copy, Download, X } from "lucide-react";
import { useChat } from "@/stores/chat";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

function previewBody(body: string, type: string) {
  if (type.includes("json") || body.trim().startsWith("{")) {
    try {
      return JSON.stringify(JSON.parse(body), null, 2);
    } catch {
      return body;
    }
  }
  return body;
}

export function ArtifactsWorkspace() {
  const artifacts = useChat((s) => s.artifacts);
  const open = useChat((s) => s.artifactsOpen);
  const width = useChat((s) => s.artifactsWidth);
  const activeId = useChat((s) => s.activeArtifactId);
  const highlight = useChat((s) => s.highlight);
  const setOpen = useChat((s) => s.setArtifactsOpen);
  const setWidth = useChat((s) => s.setArtifactsWidth);
  const setActive = useChat((s) => s.setActiveArtifact);
  const [copied, setCopied] = useState(false);
  const drag = useRef<{ startX: number; startW: number } | null>(null);
  const t = useT();

  const active = useMemo(
    () => artifacts.find((a) => a.id === (highlight && artifacts.some((x) => x.id === highlight) ? highlight : activeId)) || artifacts[artifacts.length - 1],
    [activeId, artifacts, highlight]
  );

  if (!open) return null;

  return (
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
                  onClick={() => setActive(art.id)}
                  className={cn(
                    "mb-1 w-full rounded-md px-2 py-1.5 text-start text-[11px]",
                    (active?.id === art.id || highlight === art.id) && "bg-muted text-foreground",
                    highlight === art.id && "ring-1 ring-warning"
                  )}
                >
                  <span className="block truncate font-medium">{art.title}</span>
                  <span className="block truncate text-muted-foreground">{art.type}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="fox-scroll min-w-0 flex-1 overflow-auto p-3">
            {active ? (
              <>
                <div className="mb-2 flex items-center gap-2">
                  <p className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                    {active.agent} · {t("artifacts.preview")}
                  </p>
                  <button
                    type="button"
                    className="rounded-md border border-border px-2 py-1 text-[11px]"
                    onClick={() => {
                      void navigator.clipboard.writeText(active.body || "");
                      setCopied(true);
                      window.setTimeout(() => setCopied(false), 1200);
                    }}
                  >
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    <span className="ms-1">{copied ? t("artifacts.copied") : t("artifacts.copy")}</span>
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-border px-2 py-1 text-[11px]"
                    onClick={() => {
                      const blob = new Blob([active.body || ""], { type: "text/plain" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `${active.title.replace(/\s+/g, "-")}.txt`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <Download className="me-1 inline h-3.5 w-3.5" />
                    {t("artifacts.export")}
                  </button>
                </div>
                <pre className="whitespace-pre-wrap font-mono text-[12px] leading-6">{previewBody(active.body || "", active.type)}</pre>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{t("artifacts.empty")}</p>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
