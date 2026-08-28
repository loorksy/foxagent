from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings
from app.schemas import TradeRecommendation

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class RecommendationRow(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


engine = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None
_memory_recs: dict[str, dict[str, Any]] = {}
_memory_settings: dict[str, str] = {}


async def init_db() -> None:
    global engine, SessionLocal
    settings = get_settings()
    try:
        engine = create_async_engine(settings.database_url, echo=False, future=True)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database ready (%s)", settings.database_url.split("://")[0])
    except Exception as exc:
        logger.warning("Database unavailable, using memory store: %s", exc)
        engine = None
        SessionLocal = None


async def save_recommendation(rec: TradeRecommendation) -> TradeRecommendation:
    payload = rec.model_dump(mode="json")
    if SessionLocal is None:
        _memory_recs[rec.id] = payload
        return rec
    async with SessionLocal() as session:
        row = RecommendationRow(
            id=rec.id,
            symbol=rec.symbol,
            timeframe=rec.timeframe,
            status=rec.status.value if hasattr(rec.status, "value") else str(rec.status),
            payload=json.dumps(payload, default=str),
            created_at=rec.timestamp,
        )
        await session.merge(row)
        await session.commit()
    return rec


async def list_recommendations(limit: int = 100) -> list[dict[str, Any]]:
    if SessionLocal is None:
        rows = sorted(_memory_recs.values(), key=lambda r: r.get("timestamp", ""), reverse=True)
        return rows[:limit]
    async with SessionLocal() as session:
        result = await session.execute(
            select(RecommendationRow).order_by(RecommendationRow.created_at.desc()).limit(limit)
        )
        items = []
        for row in result.scalars():
            try:
                items.append(json.loads(row.payload))
            except Exception:
                continue
        return items


async def get_recommendation(rec_id: str) -> dict[str, Any] | None:
    if SessionLocal is None:
        return _memory_recs.get(rec_id)
    async with SessionLocal() as session:
        row = await session.get(RecommendationRow, rec_id)
        if row is None:
            return None
        return json.loads(row.payload)


async def update_recommendation(rec_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    current = await get_recommendation(rec_id)
    if current is None:
        return None
    current.update(patch)
    rec = TradeRecommendation.model_validate(current)
    await save_recommendation(rec)
    return rec.model_dump(mode="json")


async def kv_set(key: str, value: str) -> None:
    if SessionLocal is None:
        _memory_settings[key] = value
        return
    async with SessionLocal() as session:
        await session.merge(SettingRow(key=key, value=value))
        await session.commit()


async def kv_get(key: str) -> str | None:
    if SessionLocal is None:
        return _memory_settings.get(key)
    async with SessionLocal() as session:
        row = await session.get(SettingRow, key)
        return None if row is None else row.value
