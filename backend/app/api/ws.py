from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth import extract_ws_token, require_token
from app.bus import bus
from app.schemas import LivePrice
from app.services.oanda import oanda
from app.services.simulator import INSTRUMENT_SPECS, simulator
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self.lock:
            self.clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self.lock:
            self.clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            dead_ok = False
            try:
                await ws.send_text(data)
            except Exception:
                dead_ok = True
            if dead_ok:
                dead.append(ws)
        for ws in dead:
            await self.remove(ws)


market_hub = Hub()


async def emit_agent(event: str, payload: dict[str, Any]) -> None:
    # SSE is the UI transport. Keep a bus publish for optional subscribers.
    await bus.publish("agent", {"type": event, "payload": payload})


async def emit_tick(price: LivePrice) -> None:
    msg = {"type": "tick", "payload": price.model_dump(mode="json")}
    await market_hub.broadcast(msg)
    await bus.publish("market", msg)


async def _simulator_ticks(instruments: list[str]) -> None:
    for inst in instruments:
        await emit_tick(simulator.tick(inst))


async def price_pump() -> None:
    """Push live ticks to /ws/market.

    OANDA configured: consume the official pricing stream (not a REST poll).
    Simulator: local tick generation. Warehouse sync is a separate task and
    never participates in this loop.
    """
    from app.services.run_control import is_paused

    instruments = list(INSTRUMENT_SPECS.keys())
    try:
        while True:
            if await is_paused():
                await asyncio.sleep(0.25)
                continue
            settings = get_settings()
            if settings.oanda_configured:
                try:
                    async for px in oanda.stream_prices(instruments):
                        if await is_paused():
                            break
                        await emit_tick(px)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("OANDA price stream ended, reconnecting: %s", exc)
                    await asyncio.sleep(1.0)
            else:
                await _simulator_ticks(instruments)
                await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        raise


async def _accept_authenticated(ws: WebSocket) -> bool:
    try:
        require_token(extract_ws_token(ws))
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return False
    await ws.accept()
    return True


@router.websocket("/ws/market")
async def market_ws(ws: WebSocket) -> None:
    if not await _accept_authenticated(ws):
        return
    await market_hub.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await market_hub.remove(ws)


