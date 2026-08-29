from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, SessionLocal
from app.schemas import utcnow


class SessionRow(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    symbol: Mapped[str] = mapped_column(String(32), default="XAU_USD")
    timeframe: Mapped[str] = mapped_column(String(16), default="15m")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


_memory: dict[str, dict[str, Any]] = {}


SESSION_ID_RE = re.compile(
    r"^(?:bc-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def new_session_id() -> str:
    return str(uuid4())


def normalize_session_id(raw: str | None) -> str:
    text = (raw or "").strip()
    if text and SESSION_ID_RE.match(text):
        return text
    return new_session_id()


def is_session_id(raw: str | None) -> bool:
    return bool(raw and SESSION_ID_RE.match(raw.strip()))


def _empty_state() -> dict[str, Any]:
    return {
        "messages": [],
        "thoughts": [],
        "tools": [],
        "debate": [],
        "artifacts": [],
        "overlays": [],
        "recalls": [],
        "recommendationId": None,
    }


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return row


async def create_session(
    symbol: str = "XAU_USD",
    timeframe: str = "15m",
    title: str = "",
    session_id: str | None = None,
) -> dict[str, Any]:
    now = utcnow()
    item = {
        "id": normalize_session_id(session_id),
        "title": title or "Untitled session",
        "symbol": symbol,
        "timeframe": timeframe,
        "state": _empty_state(),
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
    }
    if SessionLocal is None:
        _memory[item["id"]] = item
        return item
    async with SessionLocal() as session:
        session.add(
            SessionRow(
                id=item["id"],
                title=item["title"],
                symbol=symbol,
                timeframe=timeframe,
                payload=json.dumps(item["state"]),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    return item


async def list_sessions(limit: int = 80) -> list[dict[str, Any]]:
    if SessionLocal is None:
        return sorted(_memory.values(), key=lambda s: s.get("updatedAt") or "", reverse=True)[:limit]
    async with SessionLocal() as session:
        result = await session.execute(select(SessionRow).order_by(SessionRow.updated_at.desc()).limit(limit))
        out = []
        for row in result.scalars():
            out.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "symbol": row.symbol,
                    "timeframe": row.timeframe,
                    "state": json.loads(row.payload or "{}"),
                    "createdAt": row.created_at.isoformat() if row.created_at else None,
                    "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
                }
            )
        return out


async def get_session(session_id: str) -> dict[str, Any] | None:
    if SessionLocal is None:
        return _memory.get(session_id)
    async with SessionLocal() as session:
        row = await session.get(SessionRow, session_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "title": row.title,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "state": json.loads(row.payload or "{}"),
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        }


async def save_session(item: dict[str, Any]) -> dict[str, Any]:
    item["updatedAt"] = utcnow().isoformat()
    if SessionLocal is None:
        _memory[item["id"]] = item
        return item
    async with SessionLocal() as session:
        row = await session.get(SessionRow, item["id"])
        now = utcnow()
        if row is None:
            session.add(
                SessionRow(
                    id=item["id"],
                    title=item.get("title") or "",
                    symbol=item.get("symbol") or "XAU_USD",
                    timeframe=item.get("timeframe") or "15m",
                    payload=json.dumps(item.get("state") or _empty_state()),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.title = item.get("title") or row.title
            row.symbol = item.get("symbol") or row.symbol
            row.timeframe = item.get("timeframe") or row.timeframe
            row.payload = json.dumps(item.get("state") or _empty_state())
            row.updated_at = now
        await session.commit()
    return item


async def delete_session(session_id: str) -> bool:
    if SessionLocal is None:
        return _memory.pop(session_id, None) is not None
    async with SessionLocal() as session:
        row = await session.get(SessionRow, session_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def ensure_session(
    session_id: str | None,
    symbol: str = "XAU_USD",
    timeframe: str = "15m",
    title: str = "",
) -> dict[str, Any]:
    if session_id and is_session_id(session_id):
        existing = await get_session(session_id.strip())
        if existing:
            if existing.get("symbol") != symbol or existing.get("timeframe") != timeframe:
                existing["symbol"] = symbol
                existing["timeframe"] = timeframe
                await save_session(existing)
            return existing
        return await create_session(symbol, timeframe, title, session_id=session_id.strip())
    return await create_session(symbol, timeframe, title)


async def append_session_event(session_id: str, kind: str, payload: dict[str, Any]) -> None:
    item = await get_session(session_id)
    if item is None:
        return
    state = item.setdefault("state", _empty_state())
    if kind == "message":
        state.setdefault("messages", []).append(payload)
    elif kind == "thought":
        state.setdefault("thoughts", []).append(payload)
    elif kind == "tool":
        state.setdefault("tools", []).append(payload)
    elif kind == "debate":
        state.setdefault("debate", []).append(payload)
    elif kind == "artifact":
        arts = state.setdefault("artifacts", [])
        existing = next((a for a in arts if a.get("id") == payload.get("id")), None)
        if existing:
            existing.update(payload)
        else:
            arts.append(payload)
    elif kind == "recall":
        state.setdefault("recalls", []).append(payload)
    elif kind == "recommendation":
        state["recommendationId"] = payload.get("id")
        if payload.get("klineOverlays"):
            state["overlays"] = payload.get("klineOverlays")
    await save_session(item)
