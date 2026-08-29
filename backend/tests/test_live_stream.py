from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas import LivePrice
from app.services.gold_warehouse import GOLD_SYMBOL


def _tick(mid: float = 2601.25) -> LivePrice:
    return LivePrice(
        instrument=GOLD_SYMBOL,
        bid=mid - 0.1,
        ask=mid + 0.1,
        mid=mid,
        time=datetime.now(timezone.utc),
        spread=0.2,
        source="oanda",
    )


class _FakeWS:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_text(self, data: str) -> None:
        self.messages.append(json.loads(data))


@pytest.mark.asyncio
async def test_stream_prices_ticks_reach_ws_subscribers(monkeypatch):
    from app.api import ws as ws_mod

    fake = _FakeWS()
    await ws_mod.market_hub.add(fake)  # type: ignore[arg-type]
    invoked = {"n": 0}

    async def stream(instruments: list[str]):
        invoked["n"] += 1
        assert GOLD_SYMBOL in instruments
        yield _tick(2644.4)
        await asyncio.sleep(30)

    class Settings:
        oanda_configured = True

    monkeypatch.setattr(ws_mod, "get_settings", lambda: Settings())
    monkeypatch.setattr(ws_mod.oanda, "stream_prices", stream)

    task = asyncio.create_task(ws_mod.price_pump())
    for _ in range(80):
        if fake.messages:
            break
        await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await ws_mod.market_hub.remove(fake)  # type: ignore[arg-type]

    assert invoked["n"] == 1
    assert fake.messages
    assert fake.messages[0]["type"] == "tick"
    assert fake.messages[0]["payload"]["instrument"] == GOLD_SYMBOL
    assert fake.messages[0]["payload"]["mid"] == 2644.4
    assert fake.messages[0]["payload"]["source"] == "oanda"


@pytest.mark.asyncio
async def test_warehouse_sync_does_not_block_live_ticks(monkeypatch):
    from app.api import ws as ws_mod
    from app.services.gold_sync import backfill_timeframe

    fake = _FakeWS()
    await ws_mod.market_hub.add(fake)  # type: ignore[arg-type]
    sync_hold = asyncio.Event()
    sync_released = asyncio.Event()

    async def stream(_instruments: list[str]):
        n = 0
        while True:
            n += 1
            yield _tick(2600 + n * 0.01)
            await asyncio.sleep(0.03)

    async def slow_fetch(**_k):
        sync_hold.set()
        await asyncio.sleep(0.35)
        sync_released.set()
        return []

    async def sleeper(_s: float):
        return None

    class Settings:
        oanda_configured = True

    monkeypatch.setattr(ws_mod, "get_settings", lambda: Settings())
    monkeypatch.setattr(ws_mod.oanda, "stream_prices", stream)
    monkeypatch.setattr("app.db.SessionLocal", None)

    pump = asyncio.create_task(ws_mod.price_pump())
    sync = asyncio.create_task(backfill_timeframe("M15", slow_fetch, sleeper=sleeper, batch_delay=0))
    await asyncio.wait_for(sync_hold.wait(), timeout=1)
    before = len(fake.messages)
    await asyncio.sleep(0.12)
    during = len(fake.messages)
    assert during > before, "live ticks must keep flowing while warehouse fetch is blocked"
    assert not sync.done()
    await sync
    pump.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pump
    await ws_mod.market_hub.remove(fake)  # type: ignore[arg-type]
    assert sync_released.is_set()


def test_frontend_http_prices_is_explicit_ws_fallback_only():
    root = Path(__file__).resolve().parents[2]
    desk = (root / "frontend/src/components/DeskLayout.tsx").read_text(encoding="utf-8")
    canvas = (root / "frontend/src/components/ChartCanvas.tsx").read_text(encoding="utf-8")
    assert "pollWhileDisconnected" in desk
    assert "readyState !== WebSocket.OPEN" in desk
    assert 'wsUrl("/ws/market")' in desk
    assert "api.prices()" in desk
    assert "prices[symbol]" in canvas
    assert "goldWarehouse" not in canvas
    assert "gold_sync" not in canvas
    assert "gold_warehouse" not in canvas
