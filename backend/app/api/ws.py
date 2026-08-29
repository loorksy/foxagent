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
agent_hub = Hub()


async def emit_agent(event: str, payload: dict[str, Any]) -> None:
    msg = {"type": event, "payload": payload}
    await agent_hub.broadcast(msg)
    await bus.publish("agent", msg)


async def emit_tick(price: LivePrice) -> None:
    msg = {"type": "tick", "payload": price.model_dump(mode="json")}
    await market_hub.broadcast(msg)
    await bus.publish("market", msg)


async def price_pump() -> None:
    instruments = list(INSTRUMENT_SPECS.keys())
    try:
        while True:
            settings = get_settings()
            for inst in instruments:
                px = simulator.tick(inst) if not settings.oanda_configured else await oanda.get_live_price(inst)
                await emit_tick(px)
            await asyncio.sleep(0.85)
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


@router.websocket("/ws/agent")
async def agent_ws(ws: WebSocket) -> None:
    if not await _accept_authenticated(ws):
        return
    await agent_hub.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await agent_hub.remove(ws)
