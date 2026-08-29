"""XAU_USD candle warehouse — M15 / H1 / H4 / D, rolling 2-year window.

Gold-only. Other instruments keep the live OANDA/simulator path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import BigInteger, DateTime, Float, String, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas import OHLCV, utcnow
from app.services.simulator import GRANULARITY_SECONDS, normalize_granularity

logger = logging.getLogger(__name__)

GOLD_SYMBOL = "XAU_USD"
WAREHOUSE_TFS = ("M15", "H1", "H4", "D")
RETENTION_DAYS = 730
BATCH_SIZE = 5000
BATCH_DELAY_SEC = 0.4
# Stale if latest complete bar is older than 2× the bar interval (plus a small grace).
STALE_GRACE_SEC = 120

SYNC_INTERVAL_SEC = {
    "M15": 15 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
    "D": 24 * 60 * 60,
}

_memory: dict[tuple[str, int], dict[str, Any]] = {}


class GoldCandleRow(Base):
    __tablename__ = "gold_candles"

    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)
    timestamp: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), default=GOLD_SYMBOL, index=True)
    time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(16), default="simulator")
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def warehouse_tf(granularity: str) -> str | None:
    gran = normalize_granularity(granularity)
    if gran == "D1":
        gran = "D"
    return gran if gran in WAREHOUSE_TFS else None


def uses_warehouse(instrument: str, granularity: str) -> bool:
    return instrument == GOLD_SYMBOL and warehouse_tf(granularity) is not None


def interval_seconds(tf: str) -> int:
    return GRANULARITY_SECONDS.get(warehouse_tf(tf) or tf, 900)


def retention_cutoff(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=RETENTION_DAYS)


def expected_rows(tf: str, days: int = RETENTION_DAYS) -> int:
    """Trading-week estimate (5/7) so progress logs are honest about FX hours."""
    sec = interval_seconds(tf)
    return max(1, int(days * 86400 / sec * 5 / 7))


def estimated_warehouse_size() -> dict[str, Any]:
    per_tf = {tf: expected_rows(tf) for tf in WAREHOUSE_TFS}
    total = sum(per_tf.values())
    # ~160 bytes/row + two indexes ≈ 220 bytes fully loaded.
    bytes_est = total * 220
    return {
        "symbol": GOLD_SYMBOL,
        "timeframes": per_tf,
        "totalRows": total,
        "estimatedBytes": bytes_est,
        "estimatedMiB": round(bytes_est / (1024 * 1024), 2),
        "retentionDays": RETENTION_DAYS,
    }


def _row_to_ohlcv(row: GoldCandleRow | dict[str, Any]) -> OHLCV:
    if isinstance(row, dict):
        return OHLCV(
            time=row["time_utc"],
            timestamp=int(row["timestamp"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row.get("volume") or 0.0,
            complete=True,
        )
    return OHLCV(
        time=row.time_utc,
        timestamp=int(row.timestamp),
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume or 0.0,
        complete=True,
    )


def _session_factory():
    from app import db as dbmod

    return dbmod.SessionLocal


def reset_memory() -> None:
    _memory.clear()


async def upsert_candles(
    timeframe: str,
    candles: Iterable[OHLCV],
    source: str,
) -> int:
    tf = warehouse_tf(timeframe)
    if tf is None:
        return 0
    written = 0
    now = utcnow()
    session_local = _session_factory()
    payload: list[dict[str, Any]] = []
    for candle in candles:
        if candle.complete is False:
            continue
        payload.append(
            {
                "timeframe": tf,
                "timestamp": int(candle.timestamp),
                "symbol": GOLD_SYMBOL,
                "time_utc": candle.time if candle.time.tzinfo else candle.time.replace(tzinfo=timezone.utc),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "source": source,
                "inserted_at": now,
            }
        )
    if not payload:
        return 0
    if session_local is None:
        for item in payload:
            _memory[(tf, item["timestamp"])] = item
            written += 1
        return written
    async with session_local() as session:
        for item in payload:
            await session.merge(GoldCandleRow(**item))
            written += 1
        await session.commit()
    return written


async def load_latest(timeframe: str, count: int) -> list[OHLCV]:
    tf = warehouse_tf(timeframe)
    if tf is None or count <= 0:
        return []
    session_local = _session_factory()
    if session_local is None:
        rows = [v for (t, _ts), v in _memory.items() if t == tf]
        rows.sort(key=lambda r: r["timestamp"])
        return [_row_to_ohlcv(r) for r in rows[-count:]]
    async with session_local() as session:
        result = await session.execute(
            select(GoldCandleRow)
            .where(GoldCandleRow.timeframe == tf)
            .order_by(GoldCandleRow.timestamp.desc())
            .limit(count)
        )
        rows = list(result.scalars())
        rows.reverse()
        return [_row_to_ohlcv(r) for r in rows]


async def bounds(timeframe: str) -> tuple[int | None, int | None, int]:
    tf = warehouse_tf(timeframe)
    if tf is None:
        return None, None, 0
    session_local = _session_factory()
    if session_local is None:
        stamps = [ts for (t, ts) in _memory if t == tf]
        if not stamps:
            return None, None, 0
        return min(stamps), max(stamps), len(stamps)
    async with session_local() as session:
        result = await session.execute(
            select(
                func.min(GoldCandleRow.timestamp),
                func.max(GoldCandleRow.timestamp),
                func.count(GoldCandleRow.timestamp),
            ).where(GoldCandleRow.timeframe == tf)
        )
        mn, mx, n = result.one()
        return (int(mn) if mn is not None else None, int(mx) if mx is not None else None, int(n or 0))


async def prune_older_than(timeframe: str, cutoff: datetime | None = None) -> int:
    tf = warehouse_tf(timeframe)
    if tf is None:
        return 0
    cutoff = cutoff or retention_cutoff()
    cutoff_ms = int(cutoff.timestamp() * 1000)
    session_local = _session_factory()
    if session_local is None:
        keys = [k for k in _memory if k[0] == tf and k[1] < cutoff_ms]
        for key in keys:
            del _memory[key]
        return len(keys)
    async with session_local() as session:
        result = await session.execute(
            delete(GoldCandleRow).where(
                GoldCandleRow.timeframe == tf,
                GoldCandleRow.timestamp < cutoff_ms,
            )
        )
        await session.commit()
        return int(result.rowcount or 0)


def _looks_like_weekend(start: datetime, end: datetime) -> bool:
    cur = start
    while cur < end:
        wd, hour = cur.weekday(), cur.hour
        if wd == 5:
            return True
        if wd == 4 and hour >= 21:
            return True
        if wd == 6 and hour < 22:
            return True
        cur += timedelta(hours=1)
    return False


async def detect_gaps(timeframe: str, min_missing_bars: int = 2) -> list[dict[str, Any]]:
    """Scan stored timestamps for holes larger than 2 bars (weekend gaps tagged)."""
    tf = warehouse_tf(timeframe)
    if tf is None:
        return []
    interval_ms = interval_seconds(tf) * 1000
    session_local = _session_factory()
    stamps: list[int] = []
    if session_local is None:
        stamps = sorted(ts for (t, ts) in _memory if t == tf)
    else:
        async with session_local() as session:
            result = await session.execute(
                select(GoldCandleRow.timestamp)
                .where(GoldCandleRow.timeframe == tf)
                .order_by(GoldCandleRow.timestamp.asc())
            )
            stamps = [int(v) for v in result.scalars()]
    gaps: list[dict[str, Any]] = []
    for prev, nxt in zip(stamps, stamps[1:]):
        delta = nxt - prev
        missing = int(delta // interval_ms) - 1
        if missing < min_missing_bars:
            continue
        start = datetime.fromtimestamp(prev / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(nxt / 1000, tz=timezone.utc)
        gaps.append(
            {
                "fromTimestamp": prev,
                "toTimestamp": nxt,
                "fromTime": start.isoformat(),
                "toTime": end.isoformat(),
                "missingBars": missing,
                "weekend": _looks_like_weekend(start, end),
            }
        )
    return gaps


async def timeframe_health(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    frames: dict[str, Any] = {}
    for tf in WAREHOUSE_TFS:
        oldest, latest, count = await bounds(tf)
        interval = SYNC_INTERVAL_SEC[tf]
        age = None
        stale = True
        latest_iso = None
        if latest is not None:
            age = max(0.0, now.timestamp() - latest / 1000)
            stale = age > interval + interval + STALE_GRACE_SEC
            latest_iso = datetime.fromtimestamp(latest / 1000, tz=timezone.utc).isoformat()
        frames[tf] = {
            "latestTimestamp": latest,
            "latestTime": latest_iso,
            "oldestTimestamp": oldest,
            "count": count,
            "stale": stale,
            "ageSeconds": age,
            "expectedIntervalSeconds": interval,
        }
    return {
        "symbol": GOLD_SYMBOL,
        "retentionDays": RETENTION_DAYS,
        "timeframes": frames,
        "sizeEstimate": estimated_warehouse_size(),
    }
