"""Structured decision / reflection journal, adapted from TradingAgents TradingMemoryLog.

TauricResearch stores pending DECISION entries then appends REFLECTION after the
outcome is known, and injects same-ticker + cross-ticker lessons into the next run.
FoxAgent persists that journal in SQLite/Postgres with lexical embeddings for recall.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, SessionLocal
from app.schemas import utcnow

_TOKEN = re.compile(r"[a-z0-9_]+", re.I)

TERMINAL_STATUSES = {"HIT_TP1", "HIT_TP2", "STOPPED_OUT", "EXPIRED", "CANCELLED"}


class MemoryEntryRow(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # technical | macro | risk
    status: Mapped[str] = mapped_column(String(24), index=True)  # pending | resolved
    decision: Mapped[str] = mapped_column(Text, default="")
    reflection: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[str] = mapped_column(String(24), default="")
    recommendation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    outcome: Mapped[str] = mapped_column(String(32), default="")
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    embedding: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


_memory: dict[str, dict[str, Any]] = {}


def decision_summary(*, recommendation_id: str, symbol: str, action: str, rating: str = "") -> str:
    """Lightweight journal line. Full TradeRecommendation lives in recommendations.payload."""
    return f"ref={recommendation_id} symbol={symbol} action={action} rating={rating}".strip()


def embed_text(text: str) -> dict[str, float]:
    counts: Counter[str] = Counter(_TOKEN.findall((text or "").lower()))
    if not counts:
        return {}
    norm = math.sqrt(sum(c * c for c in counts.values())) or 1.0
    return {token: count / norm for token, count in counts.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    return sum(a[k] * b[k] for k in set(a) & set(b))


def _row_to_dict(row: MemoryEntryRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "kind": row.kind,
        "status": row.status,
        "decision": row.decision,
        "reflection": row.reflection,
        "rating": row.rating,
        "recommendationId": row.recommendation_id,
        "outcome": row.outcome,
        "pnl": row.pnl,
        "embedding": json.loads(row.embedding or "{}"),
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "resolvedAt": row.resolved_at.isoformat() if row.resolved_at else None,
    }


async def store_decision(
    *,
    entry_id: str,
    symbol: str,
    kind: str,
    decision: str,
    rating: str = "",
    recommendation_id: str = "",
) -> dict[str, Any]:
    payload = {
        "id": entry_id,
        "symbol": symbol,
        "kind": kind,
        "status": "pending",
        "decision": decision,
        "reflection": "",
        "rating": rating,
        "recommendationId": recommendation_id,
        "outcome": "",
        "pnl": 0.0,
        "embedding": embed_text(f"{symbol} {kind} {decision} {rating}"),
        "createdAt": utcnow().isoformat(),
        "resolvedAt": None,
    }
    if SessionLocal is None:
        _memory[entry_id] = payload
        return payload
    async with SessionLocal() as session:
        session.add(
            MemoryEntryRow(
                id=entry_id,
                symbol=symbol,
                kind=kind,
                status="pending",
                decision=decision,
                reflection="",
                rating=rating,
                recommendation_id=recommendation_id,
                outcome="",
                pnl=0.0,
                embedding=json.dumps(payload["embedding"]),
                created_at=utcnow(),
            )
        )
        await session.commit()
    return payload


async def update_with_outcome(
    *,
    recommendation_id: str,
    outcome: str,
    pnl: float,
    reflection: str,
) -> dict[str, Any] | None:
    now = utcnow()
    if SessionLocal is None:
        for item in _memory.values():
            if item.get("recommendationId") == recommendation_id and item.get("status") == "pending":
                item["status"] = "resolved"
                item["outcome"] = outcome
                item["pnl"] = pnl
                item["reflection"] = reflection
                item["resolvedAt"] = now.isoformat()
                item["embedding"] = embed_text(
                    f"{item['symbol']} {item['kind']} {item['decision']} {reflection} {outcome}"
                )
                return item
        return None
    async with SessionLocal() as session:
        result = await session.execute(
            select(MemoryEntryRow).where(
                MemoryEntryRow.recommendation_id == recommendation_id,
                MemoryEntryRow.status == "pending",
            )
        )
        row = result.scalars().first()
        if row is None:
            return None
        row.status = "resolved"
        row.outcome = outcome
        row.pnl = pnl
        row.reflection = reflection
        row.resolved_at = now
        row.embedding = json.dumps(embed_text(f"{row.symbol} {row.kind} {row.decision} {reflection} {outcome}"))
        await session.commit()
        return _row_to_dict(row)


async def list_entries(symbol: str | None = None, include_pending: bool = True) -> list[dict[str, Any]]:
    if SessionLocal is None:
        items = list(_memory.values())
        if symbol:
            items = [i for i in items if i["symbol"] == symbol]
        if not include_pending:
            items = [i for i in items if i["status"] != "pending"]
        return sorted(items, key=lambda i: i.get("createdAt") or "", reverse=True)
    async with SessionLocal() as session:
        stmt = select(MemoryEntryRow).order_by(MemoryEntryRow.created_at.desc())
        if symbol:
            stmt = stmt.where(MemoryEntryRow.symbol == symbol)
        result = await session.execute(stmt)
        items = [_row_to_dict(row) for row in result.scalars()]
        if not include_pending:
            items = [i for i in items if i["status"] != "pending"]
        return items


async def get_past_context(symbol: str, query: str = "", n_same: int = 5, n_cross: int = 3) -> str:
    """TradingAgents get_past_context: same-ticker lessons first, then cross-ticker."""
    resolved = await list_entries(include_pending=False)
    if not resolved:
        return ""
    qvec = embed_text(query or symbol)
    scored = []
    for item in resolved:
        vec = item.get("embedding") or embed_text(f"{item.get('decision')} {item.get('reflection')}")
        scored.append((cosine(qvec, vec) if qvec else 0.0, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    same, cross = [], []
    for _score, item in scored:
        if item["symbol"] == symbol and len(same) < n_same:
            same.append(item)
        elif item["symbol"] != symbol and len(cross) < n_cross:
            cross.append(item)
        if len(same) >= n_same and len(cross) >= n_cross:
            break

    parts: list[str] = []
    if same:
        parts.append(f"Past analyses of {symbol} (most recent / most similar first):")
        parts.extend(_format_full(item) for item in same)
    if cross:
        parts.append("Recent cross-instrument lessons:")
        parts.extend(_format_reflection(item) for item in cross)
    return "\n\n".join(parts)


def _format_full(item: dict[str, Any]) -> str:
    tag = f"[{item.get('createdAt')} | {item['symbol']} | {item.get('rating') or item.get('kind')} | {item.get('outcome') or 'n/a'} | pnl={item.get('pnl')}]"
    parts = [tag, f"DECISION:\n{item.get('decision') or ''}"]
    if item.get("reflection"):
        parts.append(f"REFLECTION:\n{item['reflection']}")
    return "\n\n".join(parts)


def _format_reflection(item: dict[str, Any]) -> str:
    tag = f"[{item.get('createdAt')} | {item['symbol']} | {item.get('outcome') or 'n/a'}]"
    text = item.get("reflection") or (item.get("decision") or "")[:300]
    return f"{tag}\n{text}"


async def pending_for_recommendation(recommendation_id: str) -> dict[str, Any] | None:
    items = await list_entries(include_pending=True)
    for item in items:
        if item.get("recommendationId") == recommendation_id and item.get("status") == "pending":
            return item
    return None
