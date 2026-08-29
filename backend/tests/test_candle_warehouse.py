from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import OHLCV
from app.services.gold_sync import (
    OandaRateLimitError,
    backfill_timeframe,
    fill_gap_since_latest,
    read_gold_candles,
)
from app.services.gold_warehouse import (
    GOLD_SYMBOL,
    WAREHOUSE_TFS,
    bounds,
    detect_gaps,
    estimated_warehouse_size,
    interval_seconds,
    load_latest,
    prune_older_than,
    reset_memory,
    retention_cutoff,
    timeframe_health,
    upsert_candles,
    uses_warehouse,
)


def _bar(tf: str, when: datetime, price: float = 2600.0) -> OHLCV:
    sec = interval_seconds(tf)
    epoch = int(when.timestamp())
    epoch -= epoch % sec
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return OHLCV(
        time=dt,
        timestamp=epoch * 1000,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price + 0.25,
        volume=12.0,
        complete=True,
    )


def _series(tf: str, n: int, end: datetime, price: float = 2600.0) -> list[OHLCV]:
    sec = interval_seconds(tf)
    epoch = int(end.timestamp())
    epoch -= epoch % sec
    start = epoch - sec * (n - 1)
    return [_bar(tf, datetime.fromtimestamp(start + i * sec, tz=timezone.utc), price + i * 0.1) for i in range(n)]


@pytest.fixture
def mem_warehouse(monkeypatch):
    monkeypatch.setattr("app.db.SessionLocal", None)
    reset_memory()
    yield
    reset_memory()


def test_warehouse_is_gold_only():
    assert uses_warehouse("XAU_USD", "M15")
    assert uses_warehouse("XAU_USD", "D1")
    assert not uses_warehouse("EUR_USD", "M15")
    assert not uses_warehouse("XAU_USD", "M1")
    assert not uses_warehouse("XAU_USD", "M5")


def test_size_estimate_is_documented_before_prod_backfill():
    est = estimated_warehouse_size()
    assert est["totalRows"] > 50_000
    assert est["totalRows"] < 90_000
    assert est["estimatedMiB"] < 30
    assert set(est["timeframes"]) == set(WAREHOUSE_TFS)


@pytest.mark.asyncio
async def test_backfill_batches_and_respects_rate_limit_backoff(mem_warehouse):
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    universe = _series("H1", 12, now)
    calls: list[dict] = []
    sleeps: list[float] = []
    state = {"limited": True}

    async def fetch(**kwargs):
        calls.append(kwargs)
        if state["limited"]:
            state["limited"] = False
            raise OandaRateLimitError("429 Too Many Requests")
        cursor = kwargs.get("from_time") or kwargs.get("to_time") or now
        include_first = kwargs.get("include_first")
        page = []
        for bar in universe:
            if kwargs.get("from_time"):
                if bar.time > cursor or (include_first and bar.time >= cursor):
                    page.append(bar)
            elif kwargs.get("to_time"):
                if bar.time < cursor:
                    page.append(bar)
            else:
                page.append(bar)
        size = kwargs.get("count") or 5
        if kwargs.get("to_time"):
            return page[-size:]
        return page[:size]

    async def sleeper(seconds: float):
        sleeps.append(seconds)

    result = await backfill_timeframe(
        "H1",
        fetch,
        now=now,
        sleeper=sleeper,
        batch_size=5,
        batch_delay=0.25,
        source="oanda",
    )
    assert sleeps[0] == 0.25
    assert any(s > 0.25 for s in sleeps) or len(sleeps) >= 2
    assert result["batches"] >= 2
    _, _, count = await bounds("H1")
    assert count >= 5
    assert all(c.get("count", 5) <= 5 for c in calls)


@pytest.mark.asyncio
async def test_backfill_resumes_from_last_stored_candle(mem_warehouse):
    now = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)
    universe = _series("H1", 10, now)
    released = {"n": 0}

    async def fetch(**kwargs):
        released["n"] += 1
        cursor = kwargs.get("from_time") or kwargs.get("to_time") or universe[0].time
        include_first = kwargs.get("include_first")
        if kwargs.get("to_time"):
            page = [b for b in universe if b.time < cursor]
            return page[-(kwargs.get("count") or 4) :] if released["n"] > 2 else []
        page = [
            b
            for b in universe
            if b.time > cursor or (include_first and b.time >= cursor)
        ]
        # First successful run only yields the first 4 bars, then goes empty
        # (interrupted). The next process start continues from the last stored bar.
        if released["n"] == 1:
            return page[:4]
        if released["n"] == 2:
            return []
        return page[:4]

    async def sleeper(_s):
        return None

    first = await backfill_timeframe(
        "H1", fetch, now=now, sleeper=sleeper, batch_size=4, batch_delay=0, source="oanda"
    )
    assert first["count"] == 4
    last_first = (await load_latest("H1", 1))[0].time

    second = await backfill_timeframe(
        "H1", fetch, now=now, sleeper=sleeper, batch_size=4, batch_delay=0, source="oanda"
    )
    assert second["count"] == 10
    latest = (await load_latest("H1", 1))[0]
    assert latest.time > last_first
    assert latest.timestamp == universe[-1].timestamp


@pytest.mark.asyncio
async def test_sync_fills_simulated_gap(mem_warehouse):
    now = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)  # Wednesday, no weekend in a 2-day window
    universe = _series("H1", 48, now)
    await upsert_candles("H1", [universe[0], universe[-1]], "oanda")
    gaps = await detect_gaps("H1")
    assert gaps
    assert gaps[0]["missingBars"] >= 40

    async def fetch(**kwargs):
        cursor = kwargs.get("from_time") or kwargs.get("to_time")
        include_first = kwargs.get("include_first")
        if kwargs.get("from_time"):
            page = [
                b
                for b in universe
                if b.time > cursor or (include_first and b.time >= cursor)
            ]
            return page[: kwargs.get("count") or 5000]
        if kwargs.get("to_time"):
            page = [b for b in universe if b.time < cursor]
            return page[-(kwargs.get("count") or 5000) :]
        return universe[- (kwargs.get("count") or 10) :]

    async def sleeper(_s):
        return None

    await fill_gap_since_latest("H1", fetch, now=now, sleeper=sleeper, batch_delay=0, source="oanda")
    _, _, count = await bounds("H1")
    assert count == 48
    leftover = [g for g in await detect_gaps("H1") if not g["weekend"]]
    assert leftover == []


@pytest.mark.asyncio
async def test_retention_prunes_only_older_than_two_years(mem_warehouse):
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    old = _bar("D", now - timedelta(days=800), 1800)
    keep = _bar("D", now - timedelta(days=30), 2600)
    edge = _bar("D", now - timedelta(days=729), 2400)
    await upsert_candles("D", [old, keep, edge], "oanda")
    removed = await prune_older_than("D", retention_cutoff(now))
    assert removed == 1
    stored = await load_latest("D", 10)
    stamps = {c.timestamp for c in stored}
    assert keep.timestamp in stamps
    assert edge.timestamp in stamps
    assert old.timestamp not in stamps


@pytest.mark.asyncio
async def test_get_candles_reads_warehouse_without_oanda(mem_warehouse, monkeypatch):
    now = datetime.now(timezone.utc)
    seeded = _series("M15", 40, now)
    await upsert_candles("M15", seeded, "simulator")

    async def forbidden(**_k):
        raise AssertionError("OANDA must not be called for a fully covered range")

    monkeypatch.setattr("app.services.oanda.OandaClient.fetch_remote_candles", forbidden)
    from app.services.oanda import oanda

    out = await oanda.get_candles("XAU_USD", "M15", 20)
    assert len(out) == 20
    assert out[0].timestamp >= seeded[0].timestamp
    assert out[-1].timestamp == seeded[-1].timestamp


@pytest.mark.asyncio
async def test_get_candles_fetches_only_missing_older_portion(mem_warehouse):
    now = datetime.now(timezone.utc)
    seeded = _series("M15", 10, now)
    await upsert_candles("M15", seeded, "simulator")
    older = _series("M15", 25, seeded[0].time - timedelta(seconds=interval_seconds("M15")))
    remote_calls: list[dict] = []

    async def fetch(**kwargs):
        remote_calls.append(kwargs)
        if kwargs.get("to_time"):
            return [c for c in older if c.time < kwargs["to_time"]][-20:]
        return []

    out = await read_gold_candles("M15", 25, fetch, source="simulator", now=now)
    assert remote_calls
    assert all(c.get("from_time") is None for c in remote_calls)
    assert any(c.get("to_time") is not None for c in remote_calls)
    assert len(out) == 25


@pytest.mark.asyncio
async def test_non_gold_still_hits_live_path(mem_warehouse, monkeypatch):
    calls = {"n": 0}

    async def live(*_a, **kwargs):
        calls["n"] += 1
        return _series("M15", kwargs.get("count") or 3, datetime.now(timezone.utc))

    from app.services.oanda import oanda

    monkeypatch.setattr(oanda, "fetch_remote_candles", live)
    out = await oanda.get_candles("EUR_USD", "M15", 3)
    assert calls["n"] == 1
    assert len(out) == 3


def test_health_reports_per_timeframe_latest_count_and_stale(client, auth_header, monkeypatch, mem_warehouse):
    async def fake_probe(*_a, **_k):
        return {"ok": True, "keyValid": True, "detail": "ok"}

    monkeypatch.setattr("app.api.routes.probe_anthropic", fake_probe)

    import asyncio

    now = datetime.now(timezone.utc)
    asyncio.run(upsert_candles("M15", _series("M15", 8, now), "simulator"))

    resp = client.get("/api/health", headers=auth_header)
    assert resp.status_code == 200
    warehouse = resp.json()["goldWarehouse"]
    assert warehouse["symbol"] == GOLD_SYMBOL
    m15 = warehouse["timeframes"]["M15"]
    assert m15["count"] == 8
    assert m15["latestTimestamp"]
    assert m15["stale"] is False
    assert "expectedIntervalSeconds" in m15
    assert warehouse["timeframes"]["H1"]["count"] == 0
    assert warehouse["timeframes"]["H1"]["stale"] is True

    gaps = client.get("/api/warehouse/gaps?timeframe=M15", headers=auth_header)
    assert gaps.status_code == 200
    assert gaps.json()["timeframes"]["M15"]["gapCount"] == 0


@pytest.mark.asyncio
async def test_health_snapshot_helper_stale_flag(mem_warehouse):
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    old = _bar("H4", now - timedelta(hours=20), 2500)
    await upsert_candles("H4", [old], "oanda")
    snap = await timeframe_health(now)
    assert snap["timeframes"]["H4"]["count"] == 1
    assert snap["timeframes"]["H4"]["stale"] is True
    assert snap["timeframes"]["D"]["stale"] is True
