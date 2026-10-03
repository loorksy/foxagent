"""Durable desk memory.

Ideas taken from TencentDB Agent Memory's pyramid (L0 conversation → L1 atom →
L2 scenario → L3 persona) and progressive disclosure: the next turn sees the
upper layers, and the agent drills into a row by id. Storage is the app's
SQLite/Postgres database. No Tencent Cloud account is required, and nothing
here calls an external memory vendor.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas import new_id, utcnow
from app.services.memory_log import cosine, embed_text

LAYERS = ("L0", "L1", "L2", "L3")
KINDS = ("conversation", "atom", "scenario", "persona", "preference", "constraint")
_REMEMBER = re.compile(
    r"(\bremember\b|\bdon't forget\b|\bdo not forget\b|تذكّر|تذكر|لا تنسَ|لا تنس)",
    re.I,
)
_LAYER_BOOST = {"L3": 0.18, "L2": 0.1, "L1": 0.04, "L0": 0.0}

_fallback: dict[str, dict[str, Any]] = {}


def _sessions():
    """Read the live session factory. A module-level import would stay None after init_db."""
    from app import db

    return db.SessionLocal


class LongTermMemoryRow(Base):
    __tablename__ = "long_term_memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    layer: Mapped[str] = mapped_column(String(8), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, default="XAU_USD")
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    embedding: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def _clip(text: str, limit: int = 4000) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _row_to_dict(row: LongTermMemoryRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "layer": row.layer,
        "kind": row.kind,
        "symbol": row.symbol,
        "sessionId": row.session_id,
        "text": row.text,
        "parentId": row.parent_id,
        "embedding": json.loads(row.embedding or "{}"),
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


def _public(item: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    out = {
        "id": item["id"],
        "layer": item["layer"],
        "kind": item["kind"],
        "symbol": item.get("symbol") or "XAU_USD",
        "sessionId": item.get("sessionId") or "",
        "text": item.get("text") or "",
        "parentId": item.get("parentId") or "",
        "createdAt": item.get("createdAt"),
    }
    if score is not None:
        out["score"] = round(score, 4)
    return out


async def _all_rows() -> list[dict[str, Any]]:
    sessions = _sessions()
    if sessions is None:
        return list(_fallback.values())
    async with sessions() as session:
        result = await session.execute(select(LongTermMemoryRow).order_by(LongTermMemoryRow.created_at.desc()))
        return [_row_to_dict(row) for row in result.scalars()]


async def capture_memory(
    *,
    text: str,
    layer: str = "L1",
    kind: str = "atom",
    symbol: str = "XAU_USD",
    session_id: str = "",
    parent_id: str = "",
) -> dict[str, Any]:
    cleaned = _clip(text)
    if not cleaned:
        raise ValueError("memory text is empty")
    layer_key = layer if layer in LAYERS else "L1"
    kind_key = kind if kind in KINDS else "atom"
    if layer_key == "L0" and kind_key == "atom":
        kind_key = "conversation"
    payload = {
        "id": new_id("ltm"),
        "layer": layer_key,
        "kind": kind_key,
        "symbol": (symbol or "XAU_USD").strip() or "XAU_USD",
        "sessionId": session_id or "",
        "text": cleaned,
        "parentId": parent_id or "",
        "embedding": embed_text(f"{symbol} {layer_key} {kind_key} {cleaned}"),
        "createdAt": utcnow().isoformat(),
    }
    sessions = _sessions()
    if sessions is None:
        _fallback[payload["id"]] = payload
        return _public(payload)
    async with sessions() as session:
        session.add(
            LongTermMemoryRow(
                id=payload["id"],
                layer=layer_key,
                kind=kind_key,
                symbol=payload["symbol"],
                session_id=payload["sessionId"],
                text=cleaned,
                parent_id=payload["parentId"],
                embedding=json.dumps(payload["embedding"]),
                created_at=utcnow(),
            )
        )
        await session.commit()
    return _public(payload)


async def list_long_term(symbol: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
    rows = await _all_rows()
    if symbol:
        rows = [row for row in rows if row.get("symbol") == symbol]
    rows.sort(key=lambda row: row.get("createdAt") or "", reverse=True)
    return [_public(row) for row in rows[:limit]]


def _score(query: str, item: dict[str, Any]) -> float:
    vec = item.get("embedding") or embed_text(item.get("text") or "")
    lexical = cosine(embed_text(query), vec) if query else 0.0
    return lexical + _LAYER_BOOST.get(str(item.get("layer")), 0.0)


async def search_memory(
    query: str,
    *,
    symbol: str = "XAU_USD",
    layers: tuple[str, ...] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    rows = await _all_rows()
    if symbol:
        rows = [row for row in rows if row.get("symbol") in {symbol, ""}]
    if layers:
        allowed = set(layers)
        rows = [row for row in rows if row.get("layer") in allowed]
    ranked = [(_score(query, row), row) for row in rows]
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("createdAt") or ""), reverse=True)
    return [_public(row, score) for score, row in ranked[:limit]]


async def memory_by_id(memory_id: str) -> dict[str, Any] | None:
    rows = await _all_rows()
    for row in rows:
        if row["id"] == memory_id:
            return row
    return None


async def drill_down(memory_id: str, depth: int = 4) -> list[dict[str, Any]]:
    """Persona/scenario → the source rows underneath it. Evidence stays reachable."""
    chain: list[dict[str, Any]] = []
    current = await memory_by_id(memory_id)
    seen: set[str] = set()
    while current and current["id"] not in seen and len(chain) < depth:
        seen.add(current["id"])
        chain.append(_public(current))
        parent = current.get("parentId") or ""
        current = await memory_by_id(parent) if parent else None
    return chain


async def recall_for_prompt(symbol: str, query: str = "", *, session_id: str = "") -> str:
    """Upper layers first. Raw L0 is included only when it actually matches."""
    del session_id  # turns are stored with a session id; recall is cross-session on purpose
    upper = await search_memory(query or symbol, symbol=symbol, layers=("L3", "L2", "L1"), limit=6)
    evidence = await search_memory(query or symbol, symbol=symbol, layers=("L0",), limit=2)
    lines: list[str] = []
    for item in upper:
        lines.append(f"[{item['layer']} {item['kind']} {item['id']}] {item['text']}")
    for item in evidence:
        if (item.get("score") or 0) < 0.12:
            continue
        lines.append(f"[{item['layer']} {item['kind']} {item['id']}] {item['text']}")
    if not lines:
        return ""
    return (
        "Long-term memory (L3 persona, L2 scenario, L1 atoms; call memory_recall with an id to open the source):\n"
        + "\n".join(lines)
    )[:3500]


async def record_turn(
    *,
    session_id: str,
    symbol: str,
    user_text: str,
    assistant_text: str,
) -> dict[str, Any] | None:
    user = _clip(user_text, 2000)
    assistant = _clip(assistant_text, 2000)
    if not user and not assistant:
        return None
    saved = await capture_memory(
        text=f"User: {user}\nAssistant: {assistant}",
        layer="L0",
        kind="conversation",
        symbol=symbol or "XAU_USD",
        session_id=session_id,
    )
    if user and _REMEMBER.search(user):
        await capture_memory(
            text=user,
            layer="L1",
            kind="preference",
            symbol=symbol or "XAU_USD",
            session_id=session_id,
            parent_id=saved["id"],
        )
    return saved
