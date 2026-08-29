"""General-purpose Claude Artifacts protocol.

Agents emit <antArtifact identifier type title language>...</antArtifact>
when the content is a standalone deliverable. Short chat stays in the thread.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Awaitable
from uuid import uuid4

from app.schemas import utcnow
from app.services.session_store import append_session_event

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

ARTIFACT_PROTOCOL = """
ARTIFACT PROTOCOL
You may emit zero or more Claude Artifacts. Decide dynamically — do not wrap every reply.

Create an artifact when the user asked for, or you are producing, a standalone deliverable:
1. Substantial standalone content (more than 15 lines) that will be reused or exported.
2. Code, scripts, or strategies (Python, Pine Script, MQL5, JavaScript, etc.).
3. Structured spreadsheets, CSVs, or tabular data sheets.
4. Detailed reports, guides, or markdown documents the user asked to keep.
5. Diagrams (Mermaid.js or SVG).

Do NOT create an artifact for:
- Short answers, conversational replies, or one-line confirmations
- Quick questions such as current trend, price, or bias
- Brief trade yes/no or single-level callouts
- Internal scratch reasoning

When you do create one, use this exact XML (attributes may be single- or double-quoted):
<antArtifact identifier="kebab-id" type="MIME" title="Human title" language="optional">
...content...
</antArtifact>

Valid type values:
- text/markdown
- text/plain
- text/csv
- application/vnd.ant.code   (set language=python|javascript|typescript|pine|mql5|json|…)
- application/vnd.ant.mermaid
- image/svg+xml

Keep a short chat sentence outside the tag. Never invent a deliverable the user did not ask for.
"""

OPEN_RE = re.compile(r"<antArtifact\b([^>]*)>", re.I)
CLOSE_RE = re.compile(r"</antArtifact>", re.I)
ATTR_RE = re.compile(r'([A-Za-z_:][\w:.-]*)\s*=\s*("([^"]*)"|\'([^\']*)\')')
PARTIAL_OPEN = re.compile(
    r"<(/)?(?:a|an|ant|anta|antar|antart|antarti|antartif|antartifa|antartifac|antartifact)?$",
    re.I,
)
PARTIAL_OPEN_ATTRS = re.compile(r"<antArtifact\b[^>]*$", re.I)

DELIVERABLE_RE = re.compile(
    r"\b(backtest|script|python|pine|mql5?|csv|spreadsheet|sheet|matrix|"
    r"report|guide|diagram|mermaid|artifact|code|svg)\b",
    re.I,
)
QUICK_QUESTION_RE = re.compile(
    r"^\s*(what(?:'s| is|s)?|how(?:'s| is)?|current\s+trend|trend\s*\??|price\s*\??|"
    r"bias\s*\??|now\??)\b",
    re.I,
)

MIME_ALIASES = {
    "markdown": "text/markdown",
    "md": "text/markdown",
    "text": "text/plain",
    "plain": "text/plain",
    "csv": "text/csv",
    "code": "application/vnd.ant.code",
    "python": "application/vnd.ant.code",
    "mermaid": "application/vnd.ant.mermaid",
    "svg": "image/svg+xml",
    "ict_report": "text/markdown",
    "macro_report": "text/markdown",
    "trade_blueprint": "application/vnd.ant.code",
}


def new_artifact_id() -> str:
    return f"art_{uuid4().hex[:12]}"


def normalize_artifact_type(raw: str, language: str = "") -> str:
    value = (raw or "").strip()
    lowered = value.lower()
    if lowered in MIME_ALIASES:
        return MIME_ALIASES[lowered]
    if lowered.startswith("text/") or lowered.startswith("application/") or lowered.startswith("image/"):
        return lowered
    if language and not value:
        return "application/vnd.ant.code"
    return value or "text/markdown"


def asks_for_deliverable(message: str) -> bool:
    return bool(DELIVERABLE_RE.search(message or ""))


def is_quick_question(message: str) -> bool:
    text = (message or "").strip()
    if not text or asks_for_deliverable(text):
        return False
    if len(text) <= 120 and QUICK_QUESTION_RE.search(text):
        return True
    return False


def should_publish_artifact(user_message: str, body: str) -> bool:
    """Honor agent tags except when a quick chat question would spam the drawer."""
    if is_quick_question(user_message) and not asks_for_deliverable(user_message):
        return False
    return bool((body or "").strip())


def parse_open_attrs(attr_blob: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in ATTR_RE.finditer(attr_blob or ""):
        key = match.group(1).lower()
        val = match.group(3) if match.group(3) is not None else (match.group(4) or "")
        attrs[key] = val
    ident = attrs.get("identifier") or attrs.get("id") or new_artifact_id()
    language = attrs.get("language") or attrs.get("lang") or ""
    mime = normalize_artifact_type(attrs.get("type") or attrs.get("mime") or "", language)
    if mime == "application/vnd.ant.code" and not language:
        language = attrs.get("language") or "text"
    return {
        "id": ident,
        "title": attrs.get("title") or ident,
        "type": mime,
        "language": language,
    }


def extract_artifacts(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if not text:
        return found
    pos = 0
    while True:
        open_m = OPEN_RE.search(text, pos)
        if not open_m:
            break
        close_m = CLOSE_RE.search(text, open_m.end())
        if not close_m:
            break
        meta = parse_open_attrs(open_m.group(1))
        meta["body"] = text[open_m.end() : close_m.start()]
        found.append(meta)
        pos = close_m.end()
    return found


def strip_ant_artifacts(text: str) -> str:
    if not text:
        return ""
    out = []
    pos = 0
    for match in OPEN_RE.finditer(text):
        out.append(text[pos : match.start()])
        close_m = CLOSE_RE.search(text, match.end())
        pos = close_m.end() if close_m else match.end()
        if not close_m:
            break
    out.append(text[pos:])
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def _hold_partial_tag(buf: str) -> tuple[str, str]:
    idx = buf.rfind("<")
    if idx < 0:
        return buf, ""
    tail = buf[idx:]
    if PARTIAL_OPEN.match(tail) or PARTIAL_OPEN_ATTRS.match(tail):
        return buf[:idx], tail
    return buf, ""


class ArtifactStreamParser:
    """Incremental parser for streaming <antArtifact> tags."""

    def __init__(
        self,
        emit: Emit,
        *,
        session_id: str | None,
        agent: str,
        run_id: str,
        user_message: str = "",
    ) -> None:
        self.emit = emit
        self.session_id = session_id
        self.agent = agent
        self.run_id = run_id
        self.user_message = user_message
        self.buf = ""
        self.current: dict[str, str] | None = None
        self.published: set[str] = set()

    async def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.buf += chunk
        visible: list[str] = []
        while True:
            if self.current is None:
                open_m = OPEN_RE.search(self.buf)
                if not open_m:
                    safe, self.buf = _hold_partial_tag(self.buf)
                    visible.append(safe)
                    break
                visible.append(self.buf[: open_m.start()])
                meta = parse_open_attrs(open_m.group(1))
                self.current = {**meta, "body": ""}
                self.buf = self.buf[open_m.end() :]
                if should_publish_artifact(self.user_message, "pending"):
                    await self._start(self.current)
            else:
                close_m = CLOSE_RE.search(self.buf)
                if not close_m:
                    safe, hold = _hold_partial_close(self.buf)
                    self.buf = hold
                    if safe:
                        self.current["body"] += safe
                        if self.current["id"] in self.published:
                            await self.emit(
                                "agent_artifact_delta",
                                {"id": self.current["id"], "text": safe, "runId": self.run_id},
                            )
                    break
                piece = self.buf[: close_m.start()]
                self.current["body"] += piece
                if self.current["id"] in self.published and piece:
                    await self.emit(
                        "agent_artifact_delta",
                        {"id": self.current["id"], "text": piece, "runId": self.run_id},
                    )
                await self._end(self.current)
                self.buf = self.buf[close_m.end() :]
                self.current = None
        return "".join(visible)

    async def flush(self) -> str:
        leftover = ""
        if self.current is not None:
            self.current["body"] += self.buf
            await self._end(self.current)
            self.current = None
            self.buf = ""
        else:
            leftover, self.buf = self.buf, ""
        return leftover

    async def ingest_complete(self, text: str) -> list[dict[str, str]]:
        published: list[dict[str, str]] = []
        for art in extract_artifacts(text or ""):
            if art["id"] in self.published:
                continue
            if not should_publish_artifact(self.user_message, art.get("body") or ""):
                continue
            await stream_artifact(
                self.emit,
                session_id=self.session_id,
                title=art["title"],
                artifact_type=art["type"],
                body=art["body"],
                agent=self.agent,
                run_id=self.run_id,
                identifier=art["id"],
                language=art.get("language") or "",
            )
            self.published.add(art["id"])
            published.append(art)
        return published

    async def _start(self, art: dict[str, str]) -> None:
        if art["id"] in self.published:
            return
        if is_quick_question(self.user_message) and not asks_for_deliverable(self.user_message):
            return
        payload = {
            "id": art["id"],
            "title": art["title"],
            "type": art["type"],
            "language": art.get("language") or "",
            "agent": self.agent,
            "runId": self.run_id,
        }
        await self.emit("agent_artifact_start", payload)
        self.published.add(art["id"])

    async def _end(self, art: dict[str, str]) -> None:
        if not should_publish_artifact(self.user_message, art.get("body") or ""):
            return
        if art["id"] not in self.published:
            await self._start(art)
            if art.get("body"):
                await self.emit(
                    "agent_artifact_delta",
                    {"id": art["id"], "text": art["body"], "runId": self.run_id},
                )
        artifact = {
            "id": art["id"],
            "title": art["title"],
            "type": art["type"],
            "language": art.get("language") or "",
            "agent": self.agent,
            "body": art.get("body") or "",
            "createdAt": utcnow().isoformat(),
            "runId": self.run_id,
        }
        await self.emit("agent_artifact_end", artifact)
        if self.session_id:
            await append_session_event(self.session_id, "artifact", artifact)


def _hold_partial_close(buf: str) -> tuple[str, str]:
    idx = buf.lower().rfind("</")
    if idx >= 0:
        tail = buf[idx:]
        if CLOSE_RE.match(tail):
            return buf, ""
        if re.match(r"</a(?:n(?:t(?:A(?:r(?:t(?:i(?:f(?:a(?:c(?:t(?:\s*)?)?)?)?)?)?)?)?)?)?)?$", tail, re.I):
            return buf[:idx], tail
    return buf, ""


async def stream_artifact(
    emit: Emit,
    *,
    session_id: str | None,
    title: str,
    artifact_type: str,
    body: str,
    agent: str,
    run_id: str,
    identifier: str | None = None,
    language: str = "",
) -> dict[str, Any]:
    mime = normalize_artifact_type(artifact_type, language)
    artifact = {
        "id": identifier or new_artifact_id(),
        "title": title,
        "type": mime,
        "language": language,
        "agent": agent,
        "body": "",
        "createdAt": utcnow().isoformat(),
        "runId": run_id,
    }
    await emit(
        "agent_artifact_start",
        {k: artifact[k] for k in ("id", "title", "type", "language", "agent", "runId")},
    )
    chunk = 280
    acc = []
    for i in range(0, len(body), chunk):
        part = body[i : i + chunk]
        acc.append(part)
        await emit("agent_artifact_delta", {"id": artifact["id"], "text": part, "runId": run_id})
    artifact["body"] = "".join(acc)
    await emit("agent_artifact_end", artifact)
    if session_id:
        await append_session_event(session_id, "artifact", artifact)
    return artifact
