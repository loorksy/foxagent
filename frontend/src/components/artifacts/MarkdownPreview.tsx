"use client";

import type { ReactElement } from "react";

function inline(text: string) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(/`([^`]+)`/g, '<code class="art-code">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function isTableRow(line: string) {
  return /^\s*\|.+\|\s*$/.test(line);
}

function isSep(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

export function MarkdownPreview({ body }: { body: string }) {
  const lines = (body || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactElement[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push(
        <pre key={key++} className="art-fence" data-lang={lang}>
          {buf.join("\n")}
        </pre>
      );
      continue;
    }
    if (isTableRow(line) && i + 1 < lines.length && isSep(lines[i + 1])) {
      const header = line.split("|").slice(1, -1).map((c) => c.trim());
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i += 1;
      }
      blocks.push(
        <div key={key++} className="art-table-wrap">
          <table className="art-table">
            <thead>
              <tr>
                {header.map((h, hi) => (
                  <th key={hi} dangerouslySetInnerHTML={{ __html: inline(h) }} />
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((c, ci) => (
                    <td key={ci} dangerouslySetInnerHTML={{ __html: inline(c) }} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const Tag = (`h${heading[1].length}` as unknown) as "h1";
      blocks.push(<Tag key={key++} className={`art-h art-h${heading[1].length}`} dangerouslySetInnerHTML={{ __html: inline(heading[2]) }} />);
      i += 1;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ul key={key++} className="art-ul">
          {items.map((item, ii) => (
            <li key={ii} dangerouslySetInnerHTML={{ __html: inline(item) }} />
          ))}
        </ul>
      );
      continue;
    }
    const para: string[] = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !lines[i].startsWith("```") && !isTableRow(lines[i])) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={key++} className="art-p" dangerouslySetInnerHTML={{ __html: inline(para.join(" ")) }} />);
  }
  return <div className="art-md">{blocks}</div>;
}
