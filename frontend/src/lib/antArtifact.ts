export type ParsedArtifact = {
  id: string;
  title: string;
  type: string;
  language: string;
  body: string;
};

const OPEN_RE = /<antArtifact\b([^>]*)>/i;
const CLOSE_RE = /<\/antArtifact>/i;
const ATTR_RE = /([A-Za-z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;

const MIME_ALIASES: Record<string, string> = {
  markdown: "text/markdown",
  md: "text/markdown",
  text: "text/plain",
  plain: "text/plain",
  csv: "text/csv",
  code: "application/vnd.ant.code",
  python: "application/vnd.ant.code",
  mermaid: "application/vnd.ant.mermaid",
  svg: "image/svg+xml",
  ict_report: "text/markdown",
  macro_report: "text/markdown",
  trade_blueprint: "application/vnd.ant.code",
};

export type PreviewKind = "markdown" | "code" | "csv" | "mermaid" | "svg" | "plain";

export function normalizeArtifactType(raw: string, language = ""): string {
  const value = (raw || "").trim();
  const lowered = value.toLowerCase();
  if (MIME_ALIASES[lowered]) return MIME_ALIASES[lowered];
  if (lowered.startsWith("text/") || lowered.startsWith("application/") || lowered.startsWith("image/")) {
    return lowered;
  }
  if (language && !value) return "application/vnd.ant.code";
  return value || "text/markdown";
}

export function previewKind(type: string, language = ""): PreviewKind {
  const mime = normalizeArtifactType(type, language);
  if (mime === "text/csv" || mime.endsWith("+csv")) return "csv";
  if (mime === "application/vnd.ant.mermaid" || mime.includes("mermaid")) return "mermaid";
  if (mime === "image/svg+xml" || mime.includes("svg")) return "svg";
  if (mime === "application/vnd.ant.code" || mime.includes("code") || language) return "code";
  if (mime === "text/plain") return "plain";
  return "markdown";
}

export function parseOpenAttrs(blob: string): Omit<ParsedArtifact, "body"> {
  const attrs: Record<string, string> = {};
  ATTR_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = ATTR_RE.exec(blob || ""))) {
    attrs[match[1].toLowerCase()] = match[2] ?? match[3] ?? "";
  }
  const language = attrs.language || attrs.lang || "";
  return {
    id: attrs.identifier || attrs.id || `art_${Math.random().toString(36).slice(2, 10)}`,
    title: attrs.title || attrs.identifier || "Artifact",
    type: normalizeArtifactType(attrs.type || attrs.mime || "", language),
    language,
  };
}

export function extractArtifacts(text: string): ParsedArtifact[] {
  const found: ParsedArtifact[] = [];
  if (!text) return found;
  let pos = 0;
  while (pos < text.length) {
    const rest = text.slice(pos);
    const open = OPEN_RE.exec(rest);
    if (!open) break;
    const afterOpen = pos + open.index + open[0].length;
    const close = CLOSE_RE.exec(text.slice(afterOpen));
    if (!close) break;
    const meta = parseOpenAttrs(open[1] || "");
    found.push({
      ...meta,
      body: text.slice(afterOpen, afterOpen + close.index),
    });
    pos = afterOpen + close.index + close[0].length;
  }
  return found;
}

export function stripAntArtifacts(text: string): string {
  if (!text) return "";
  return text.replace(/<antArtifact\b[^>]*>[\s\S]*?<\/antArtifact>/gi, "").replace(/\n{3,}/g, "\n\n").trim();
}

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let i = 0;
  let quoted = false;
  const src = text.replace(/^\uFEFF/, "");
  while (i < src.length) {
    const ch = src[i];
    if (quoted) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          cell += '"';
          i += 2;
          continue;
        }
        quoted = false;
        i += 1;
        continue;
      }
      cell += ch;
      i += 1;
      continue;
    }
    if (ch === '"') {
      quoted = true;
      i += 1;
      continue;
    }
    if (ch === ",") {
      row.push(cell);
      cell = "";
      i += 1;
      continue;
    }
    if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      i += 1;
      continue;
    }
    cell += ch;
    i += 1;
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  const width = rows.reduce((m, r) => Math.max(m, r.length), 0);
  return rows.map((r) => {
    const copy = r.slice();
    while (copy.length < width) copy.push("");
    return copy;
  });
}

export function toCsv(rows: string[][]): string {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          const value = cell ?? "";
          if (/[",\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
          return value;
        })
        .join(",")
    )
    .join("\n");
}

export const CODE_LANGUAGES = [
  "python",
  "javascript",
  "typescript",
  "pine",
  "mql5",
  "json",
  "html",
  "css",
  "sql",
  "bash",
  "text",
];
