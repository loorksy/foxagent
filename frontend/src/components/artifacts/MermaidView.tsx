"use client";

import { useEffect, useId, useState } from "react";
import { useT } from "@/i18n";

export function MermaidView({ body }: { body: string }) {
  const t = useT();
  const reactId = useId().replace(/:/g, "");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function render() {
      if (!body.trim()) {
        setSvg("");
        return;
      }
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "strict",
          fontFamily: "JetBrains Mono, ui-monospace, monospace",
        });
        const id = `mmd_${reactId}_${Math.random().toString(36).slice(2, 8)}`;
        const result = await mermaid.render(id, body);
        if (!cancelled) {
          setError("");
          setSvg(result.svg);
        }
      } catch (err) {
        if (!cancelled) {
          setSvg("");
          setError(err instanceof Error ? err.message : t("artifacts.diagramError"));
        }
      }
    }
    void render();
    return () => {
      cancelled = true;
    };
  }, [body, reactId, t]);

  if (error) {
    return (
      <div>
        <p className="mb-2 text-xs text-sell">{error}</p>
        <pre className="whitespace-pre-wrap font-mono text-[12px]">{body}</pre>
      </div>
    );
  }
  if (!svg) return <p className="text-sm text-muted-foreground">{t("artifacts.preview")}</p>;
  return <div className="art-mermaid" dangerouslySetInnerHTML={{ __html: svg }} />;
}
