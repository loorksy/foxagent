"""24/7 XAU_USD warehouse sync: resumable 2-year backfill + gap recovery.

Runs as a FastAPI lifespan asyncio task, same pattern as price_pump and
_reflection_loop. There is no PM2 process manager in this repo.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.schemas import OHLCV
from app.services.gold_warehouse import (
    BATCH_DELAY_SEC,
    BATCH_SIZE,
    GOLD_SYMBOL,
    RETENTION_DAYS,
    WAREHOUSE_TFS,
    bounds,
    detect_gaps,
    expected_rows,
    interval_seconds,
    prune_older_than,
    retention_cutoff,
    upsert_candles,
    warehouse_tf,
)
from app.services.simulator import normalize_granularity

logger = logging.getLogger(__name__)

FetchPage = Callable[..., Awaitable[list[OHLCV]]]
Sleeper = Callable[[float], Awaitable[None]]


class OandaRateLimitError(Exception):
    pass


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def fetch_page_with_backoff(
    fetch: FetchPage,
    *,
    sleeper: Sleeper,
    batch_delay: float,
    **kwargs: Any,
) -> list[OHLCV]:
    delay = max(batch_delay, 0.05)
    last_exc: Exception | None = None
    for attempt in range(6):
        try:
            return await fetch(**kwargs)
        except OandaRateLimitError as exc:
            last_exc = exc
            logger.warning("OANDA rate limit on gold warehouse fetch, backing off %.2fs", delay)
            await sleeper(delay)
            delay *= 2
        except Exception as exc:
            last_exc = exc
            logger.warning("Gold warehouse fetch failed (attempt %s): %s", attempt + 1, exc)
            await sleeper(delay)
            delay *= 2
    if last_exc:
        raise last_exc
    return []


async def backfill_timeframe(
    timeframe: str,
    fetch: FetchPage,
    *,
    now: datetime | None = None,
    sleeper: Sleeper | None = None,
    batch_size: int = BATCH_SIZE,
    batch_delay: float = BATCH_DELAY_SEC,
    source: str = "oanda",
) -> dict[str, Any]:
    """Fill from the 2-year window start up to `now`, resuming from the last stored bar."""
    tf = warehouse_tf(timeframe)
    if tf is None:
        raise ValueError(f"unsupported warehouse timeframe: {timeframe}")
    sleeper = sleeper or _default_sleep
    now = now or datetime.now(timezone.utc)
    window_start = retention_cutoff(now)
    interval = interval_seconds(tf)
    target = expected_rows(tf)
    batches = 0
    wrote = 0

    oldest, newest, count = await bounds(tf)
    # Resume forward from last stored candle (or the window start if empty).
    if newest is None:
        cursor = window_start
        include_first = True
    else:
        cursor = datetime.fromtimestamp(newest / 1000, tz=timezone.utc)
        include_first = False

    while cursor < now:
        page = await fetch_page_with_backoff(
            fetch,
            sleeper=sleeper,
            batch_delay=batch_delay,
            instrument=GOLD_SYMBOL,
            granularity=tf,
            from_time=cursor,
            count=batch_size,
            include_first=include_first,
        )
        batches += 1
        include_first = False
        newer = [c for c in page if c.complete is not False and c.time > cursor]
        if not newer:
            break
        wrote += await upsert_candles(tf, newer, source)
        cursor = newer[-1].time
        _, _, count = await bounds(tf)
        logger.info("Backfilled %s: %s/%s candles", tf, f"{count:,}", f"{target:,}")
        if len(newer) < 2 and (now - cursor).total_seconds() < interval:
            break
        await sleeper(batch_delay)

    # Backward fill if the oldest stored bar is still inside the 2-year window
    # (e.g. a live read stored only the last 300 bars, then the job started).
    oldest, newest, count = await bounds(tf)
    if oldest is not None:
        cursor = datetime.fromtimestamp(oldest / 1000, tz=timezone.utc)
        while cursor > window_start:
            page = await fetch_page_with_backoff(
                fetch,
                sleeper=sleeper,
                batch_delay=batch_delay,
                instrument=GOLD_SYMBOL,
                granularity=tf,
                to_time=cursor,
                count=batch_size,
                include_first=False,
            )
            batches += 1
            older = [c for c in page if c.complete is not False and c.time < cursor]
            if not older:
                break
            wrote += await upsert_candles(tf, older, source)
            cursor = older[0].time
            _, _, count = await bounds(tf)
            logger.info("Backfilled %s: %s/%s candles", tf, f"{count:,}", f"{target:,}")
            await sleeper(batch_delay)

    # Mid-range holes (downtime) — skip weekend FX closures.
    for gap in await detect_gaps(tf):
        if gap["weekend"]:
            continue
        start = datetime.fromtimestamp(gap["fromTimestamp"] / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(gap["toTimestamp"] / 1000, tz=timezone.utc)
        page = await fetch_page_with_backoff(
            fetch,
            sleeper=sleeper,
            batch_delay=batch_delay,
            instrument=GOLD_SYMBOL,
            granularity=tf,
            from_time=start,
            count=batch_size,
            include_first=False,
        )
        batches += 1
        mid = [c for c in page if c.complete is not False and start < c.time < end]
        if mid:
            wrote += await upsert_candles(tf, mid, source)
            _, _, count = await bounds(tf)
            logger.info("Backfilled %s: %s/%s candles", tf, f"{count:,}", f"{target:,}")
        await sleeper(batch_delay)

    pruned = await prune_older_than(tf, window_start)
    _, _, count = await bounds(tf)
    return {"timeframe": tf, "count": count, "wrote": wrote, "batches": batches, "pruned": pruned}


async def fill_gap_since_latest(
    timeframe: str,
    fetch: FetchPage,
    *,
    now: datetime | None = None,
    sleeper: Sleeper | None = None,
    batch_size: int = BATCH_SIZE,
    batch_delay: float = BATCH_DELAY_SEC,
    source: str = "oanda",
) -> dict[str, Any]:
    """Fetch everything after the last stored bar (restart / downtime recovery)."""
    return await backfill_timeframe(
        timeframe,
        fetch,
        now=now,
        sleeper=sleeper,
        batch_size=batch_size,
        batch_delay=batch_delay,
        source=source,
    )


async def run_sync_cycle(
    fetch: FetchPage,
    *,
    now: datetime | None = None,
    sleeper: Sleeper | None = None,
    source: str = "oanda",
) -> dict[str, Any]:
    results = []
    for tf in WAREHOUSE_TFS:
        results.append(
            await backfill_timeframe(tf, fetch, now=now, sleeper=sleeper, source=source)
        )
        await prune_older_than(tf, retention_cutoff(now))
    return {"results": results, "retentionDays": RETENTION_DAYS}


async def gold_sync_loop() -> None:
    import os

    from app.config import get_settings
    from app.services.oanda import oanda
    from app.services.run_control import is_paused

    flag = os.environ.get("GOLD_WAREHOUSE_SYNC", "1").strip().lower()
    if flag in {"0", "false", "off", "no"} or os.environ.get("PYTEST_CURRENT_TEST"):
        logger.info("Gold warehouse background sync is disabled in this process")
        return

    await asyncio.sleep(4)
    logger.info(
        "Gold candle warehouse sync starting (%s, %s-day window)",
        ",".join(WAREHOUSE_TFS),
        RETENTION_DAYS,
    )
    while True:
        try:
            if not await is_paused():
                settings = get_settings()
                source = "oanda" if settings.oanda_configured else "simulator"
                await run_sync_cycle(oanda.fetch_remote_candles, source=source)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Gold warehouse sync cycle failed: %s", exc)
        await asyncio.sleep(60)


async def read_gold_candles(
    granularity: str,
    count: int,
    fetch: FetchPage,
    *,
    source: str = "oanda",
    now: datetime | None = None,
) -> list[OHLCV]:
    """Serve a request from the warehouse, fetching only missing ranges."""
    from app.services.gold_warehouse import load_latest

    tf = warehouse_tf(granularity) or normalize_granularity(granularity)
    now = now or datetime.now(timezone.utc)
    stored = await load_latest(tf, count)
    interval = interval_seconds(tf)

    if not stored:
        page = await fetch(
            instrument=GOLD_SYMBOL,
            granularity=tf,
            count=min(max(count, 2), BATCH_SIZE),
        )
        complete = [c for c in page if c.complete is not False]
        if complete:
            await upsert_candles(tf, complete, source)
            stored = await load_latest(tf, count)
        return stored[-count:] if stored else []

    if len(stored) < count:
        oldest = stored[0].time
        missing = count - len(stored) + 2
        page = await fetch(
            instrument=GOLD_SYMBOL,
            granularity=tf,
            to_time=oldest,
            count=min(max(missing, 2), BATCH_SIZE),
            include_first=False,
        )
        older = [c for c in page if c.complete is not False and c.timestamp < stored[0].timestamp]
        if older:
            await upsert_candles(tf, older, source)
            stored = await load_latest(tf, count)

    newest = stored[-1].time if stored else None
    # last_ts is bar open; the next closed bar exists only after 2 intervals.
    stale = newest is None or (now - newest).total_seconds() >= 2 * interval
    if stale and newest is not None:
        page = await fetch(
            instrument=GOLD_SYMBOL,
            granularity=tf,
            from_time=newest,
            count=min(max(count, 2), BATCH_SIZE),
            include_first=False,
        )
        newer = [c for c in page if c.complete is not False and c.time > newest]
        if newer:
            await upsert_candles(tf, newer, source)
            stored = await load_latest(tf, count)

    return stored[-count:] if stored else []


async def gap_report(timeframe: str | None = None) -> dict[str, Any]:
    frames = [warehouse_tf(timeframe)] if timeframe else list(WAREHOUSE_TFS)
    frames = [tf for tf in frames if tf]
    out = {}
    for tf in frames:
        gaps = await detect_gaps(tf)
        unexpected = [g for g in gaps if not g["weekend"]]
        out[tf] = {
            "gaps": gaps,
            "gapCount": len(gaps),
            "unexpectedGapCount": len(unexpected),
        }
    return {"symbol": GOLD_SYMBOL, "timeframes": out}
