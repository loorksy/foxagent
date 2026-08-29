from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.db import get_recommendation, list_recommendations, update_recommendation
from app.services.mcp_tools import persist_recommendation
from app.services.risk_rules import RiskRejected
from app.schemas import CandleRequest, ChatRequest, SessionCreate, SessionUpdate, SettingsPayload, TradeRecommendation
from app.services.agent import run_chat
from app.services.memory_log import TERMINAL_STATUSES, get_past_context, list_entries
from app.services.reflection import write_reflection
from app.services.session_store import (
    create_session,
    delete_session,
    ensure_session,
    get_session,
    list_sessions,
    save_session,
)
from app.services.analysis import analyze_structure, structure_summary
from app.services.chart_capture import render_candles_b64
from app.services.oanda import oanda
from app.services.settings_store import (
    load_runtime_settings,
    probe_anthropic,
    save_runtime_settings,
    to_public,
    validate_anthropic_key,
    validate_oanda,
)
from app.services.telegram_service import send_test_ping
from app.services.simulator import INSTRUMENT_SPECS, normalize_granularity
from app.api.ws import emit_agent

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    runtime = await load_runtime_settings()
    probe = await probe_anthropic(live_completion=True, use_cache=True)
    configured = bool(runtime.anthropicApiKey)
    return {
        "ok": True,
        "service": settings.app_name,
        "dataMode": "oanda" if runtime.oandaApiToken and runtime.oandaAccountId else "simulator",
        "anthropic": bool(probe.get("ok")),
        "anthropicConfigured": configured,
        "anthropicKeyValid": bool(probe.get("keyValid")),
        "anthropicReady": bool(probe.get("ok")),
        "anthropicDetail": probe.get("detail") or "",
    }


@router.get("/instruments")
async def instruments() -> dict:
    items = [
        {
            "ticker": k,
            "symbol": k,
            "display": v["display"],
            "name": v["name"],
            "pricePrecision": v["decimals"],
            "pip": v["pip"],
        }
        for k, v in INSTRUMENT_SPECS.items()
    ]
    return {"instruments": items}


@router.get("/candles")
async def candles(instrument: str = "XAU_USD", granularity: str = "M15", count: int = 300) -> dict:
    gran = normalize_granularity(granularity)
    data = await oanda.get_candles(instrument, gran, count)
    return {
        "instrument": instrument,
        "granularity": gran,
        "candles": [c.to_kline() for c in data],
    }


@router.post("/candles")
async def candles_post(body: CandleRequest) -> dict:
    return await candles(body.instrument, body.granularity, body.count)


@router.get("/price")
async def price(instrument: str = "XAU_USD") -> dict:
    px = await oanda.get_live_price(instrument)
    return px.model_dump(mode="json")


@router.get("/prices")
async def prices() -> dict:
    from app.services.simulator import INSTRUMENT_SPECS

    out = []
    for inst in INSTRUMENT_SPECS:
        px = await oanda.get_live_price(inst)
        out.append(px.model_dump(mode="json"))
    return {"prices": out}


@router.get("/structure")
async def structure(instrument: str = "XAU_USD", granularity: str = "M15", count: int = 300) -> dict:
    data = await oanda.get_candles(instrument, granularity, count)
    return structure_summary(analyze_structure(data))


@router.get("/chart-snapshot")
async def chart_snapshot(instrument: str = "XAU_USD", granularity: str = "M15") -> dict:
    data = await oanda.get_candles(instrument, granularity, 180)
    return {"image": render_candles_b64(data, f"{instrument} {granularity}"), "mime": "image/png"}


@router.get("/recommendations")
async def recs() -> dict:
    return {"recommendations": await list_recommendations(200)}


@router.get("/recommendations/{rec_id}")
async def rec_one(rec_id: str) -> dict:
    item = await get_recommendation(rec_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.post("/recommendations")
async def rec_create(body: TradeRecommendation) -> dict:
    try:
        result = await persist_recommendation(body.model_dump(mode="json"), emit_agent)
    except RiskRejected as exc:
        raise HTTPException(400, {"detail": "Risk gate rejected", "reasons": exc.result.get("reasons"), "gate": exc.result}) from exc
    return result["recommendation"]


@router.patch("/recommendations/{rec_id}")
async def rec_patch(rec_id: str, patch: dict = Body(...)) -> dict:
    updated = await update_recommendation(rec_id, patch)
    if not updated:
        raise HTTPException(404, "Not found")
    status = str(updated.get("status") or "")
    if status in TERMINAL_STATUSES:
        try:
            await write_reflection(rec_id, status, float(updated.get("pnlPips") or 0.0))
        except Exception:
            pass
    return updated


@router.get("/sessions")
async def sessions_list() -> dict:
    return {"sessions": await list_sessions(80)}


@router.post("/sessions")
async def sessions_create(body: SessionCreate | None = None) -> dict:
    payload = body or SessionCreate()
    if payload.id:
        return await ensure_session(payload.id, payload.symbol, payload.timeframe, payload.title)
    return await create_session(payload.symbol, payload.timeframe, payload.title)


@router.get("/sessions/{session_id}")
async def sessions_get(session_id: str) -> dict:
    item = await get_session(session_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.put("/sessions/{session_id}")
async def sessions_put(session_id: str, body: SessionUpdate) -> dict:
    item = await get_session(session_id)
    if not item:
        item = await ensure_session(session_id, body.symbol or "XAU_USD", body.timeframe or "15m", body.title or "")
    if body.title is not None:
        item["title"] = body.title
    if body.symbol is not None:
        item["symbol"] = body.symbol
    if body.timeframe is not None:
        item["timeframe"] = body.timeframe
    if body.state is not None:
        item["state"] = body.state
    return await save_session(item)


@router.delete("/sessions/{session_id}")
async def sessions_delete(session_id: str) -> dict:
    ok = await delete_session(session_id)
    if not ok:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/memory")
async def memory_list(symbol: str | None = None) -> dict:
    return {"entries": await list_entries(symbol=symbol, include_pending=True)}


@router.get("/memory/context")
async def memory_context(symbol: str = "XAU_USD", query: str = "") -> dict:
    text = await get_past_context(symbol, query=query)
    return {"symbol": symbol, "context": text}


@router.get("/settings")
async def settings_get() -> dict:
    payload = await load_runtime_settings()
    return to_public(payload).model_dump()


@router.put("/settings")
async def settings_put(body: SettingsPayload) -> dict:
    public = await save_runtime_settings(body)
    return public.model_dump()


@router.post("/settings/validate")
async def settings_validate(body: dict) -> dict:
    target = body.get("target")
    if target == "anthropic":
        return await validate_anthropic_key(body.get("anthropicApiKey") or "")
    if target == "oanda":
        return await validate_oanda(
            body.get("oandaApiToken") or "",
            body.get("oandaAccountId") or "",
            body.get("oandaEnvironment") or "",
        )
    if target == "telegram":
        runtime = await load_runtime_settings()
        token = body.get("telegramBotToken") or runtime.telegramBotToken
        chat = body.get("telegramChatId") or runtime.telegramChatId
        return await send_test_ping(token, chat)
    return {"ok": False, "detail": "Unknown target"}


@router.post("/agent/chat")
async def agent_chat(body: ChatRequest) -> dict:
    result = await run_chat(body, emit_agent)
    return result


@router.post("/agent/chat/stream")
async def agent_chat_stream(body: ChatRequest):
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(event: str, payload: dict) -> None:
        await queue.put({"type": event, "payload": payload})
        await emit_agent(event, payload)

    async def runner() -> None:
        try:
            await run_chat(body, emit)
        except Exception as exc:
            await queue.put({"type": "error", "payload": {"detail": str(exc)}})
        finally:
            await queue.put(None)

    async def gen():
        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/models")
async def models() -> dict:
    return {
        "models": [
            {"id": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "badge": "Default"},
            {"id": "claude-3-7-sonnet-latest", "label": "Claude 3.7 Sonnet", "badge": "Vision"},
            {"id": "claude-3-5-sonnet-latest", "label": "Claude 3.5 Sonnet", "badge": "Stable"},
            {"id": "claude-3-5-haiku-latest", "label": "Claude 3.5 Haiku", "badge": "Fast"},
            {"id": "claude-opus-4-5", "label": "Claude Opus 4.5", "badge": "Max"},
        ]
    }
