from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.db import list_recommendations, update_recommendation
from app.services.run_control import is_paused, request_cancel, set_paused
from app.schemas import ChatRequest, SessionCreate, SessionUpdate, SettingsPayload
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
    from app.services.sdk_runtime import stats as sdk_stats

    return {
        "ok": True,
        "service": settings.app_name,
        "dataMode": "oanda" if runtime.oandaApiToken and runtime.oandaAccountId else "simulator",
        "anthropic": bool(probe.get("ok")),
        "anthropicConfigured": configured,
        "anthropicKeyValid": bool(probe.get("keyValid")),
        "anthropicReady": bool(probe.get("ok")),
        "anthropicDetail": probe.get("detail") or "",
        **sdk_stats.snapshot(),
        "goldWarehouse": await _gold_warehouse_health(),
    }


async def _gold_warehouse_health() -> dict:
    from app.services.gold_warehouse import timeframe_health

    return await timeframe_health()


@router.get("/warehouse/gaps")
async def warehouse_gaps(timeframe: str | None = None) -> dict:
    from app.services.gold_sync import gap_report

    return await gap_report(timeframe)


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


@router.get("/prices")
async def prices() -> dict:
    """HTTP fallback for live prices when /ws/market is disconnected."""
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


@router.get("/recommendations")
async def recs() -> dict:
    return {"recommendations": await list_recommendations(200)}


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
    # Client PUT is limited to operator-owned fields (title, symbol, timeframe,
    # overlays, artifacts). Thoughts/tools/debate/recalls/messages are
    # server-authoritative via append_session_event so a stale persistActive
    # cannot drop transcript rows the crew already wrote.
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
        state = item.setdefault("state", {})
        incoming = body.state
        if "overlays" in incoming:
            state["overlays"] = incoming.get("overlays") or []
        if "artifacts" in incoming:
            state["artifacts"] = incoming.get("artifacts") or []
        if incoming.get("recommendationId") and not state.get("recommendationId"):
            state["recommendationId"] = incoming.get("recommendationId")
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
    if target == "metaapi":
        from app.services.metaapi import validate_metaapi

        return await validate_metaapi(
            body.get("metaapiToken") or "",
            body.get("metaapiAccountId") or "",
        )
    return {"ok": False, "detail": "Unknown target"}


@router.get("/mt5/status")
async def mt5_status() -> dict:
    from app.services.metaapi import get_status

    return await get_status()


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

    run_box: dict[str, str | None] = {"id": body.sessionId}

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
                if item.get("type") == "run_start":
                    run_box["id"] = (item.get("payload") or {}).get("runId") or run_box["id"]
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            if run_box.get("id"):
                request_cancel(str(run_box["id"]))
            if not task.done():
                task.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/agent/chat/stream/cancel")
async def agent_chat_cancel(body: dict = Body(...)) -> dict:
    run_id = str(body.get("runId") or body.get("run_id") or "")
    ok = request_cancel(run_id)
    return {"ok": ok, "runId": run_id, "cancelled": ok}


@router.get("/system/status")
async def system_status() -> dict:
    return {"paused": await is_paused()}


@router.post("/system/pause")
async def system_pause() -> dict:
    await set_paused(True)
    return {"paused": True}


@router.post("/system/resume")
async def system_resume() -> dict:
    await set_paused(False)
    return {"paused": False}


@router.get("/economic-calendar")
async def economic_calendar(hours_ahead: int = 24, min_impact: str = "medium") -> dict:
    from app.services.mcp_tools import tool_get_economic_calendar

    payload = await tool_get_economic_calendar("XAU_USD", hours_ahead, min_impact)
    return {
        "events": payload.get("events") or [],
        "source": payload.get("source") or "session-clock",
        "cached": bool(payload.get("cached")),
        "warning": payload.get("warning") or "",
        "session": payload.get("session"),
        "windows": payload.get("windows") or [],
        "note": payload.get("note") or "",
    }


@router.get("/economic-calendar/upcoming")
async def economic_calendar_upcoming() -> dict:
    return await economic_calendar(hours_ahead=48, min_impact="medium")


@router.get("/inbox")
async def inbox_list(tab: str | None = None) -> dict:
    from app.services.inbox import snapshot

    return await snapshot(tab)


@router.get("/inbox/summary")
async def inbox_summary() -> dict:
    from app.services.inbox import desk_status, list_items, snapshot

    items = await list_items()
    desk = await desk_status()
    snap = await snapshot()
    return {"openCount": desk.get("openCount") or 0, "counts": snap.get("counts"), "desk": desk, "items": items[:8]}


@router.get("/inbox/{item_id}")
async def inbox_item(item_id: str) -> dict:
    from app.services.inbox import get_item

    item = await get_item(item_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.post("/inbox/{item_id}/ack")
async def inbox_ack(item_id: str) -> dict:
    from app.services.inbox import ack_item

    result = await ack_item(item_id)
    if not result.get("ok"):
        raise HTTPException(400, str(result.get("detail") or "Cannot ack"))
    return result


@router.get("/approvals")
async def approvals_list() -> dict:
    from app.services.inbox import snapshot

    return await snapshot("approvals")


@router.post("/approvals/{item_id}/approve")
async def approvals_approve(item_id: str) -> dict:
    from app.services.inbox import approve_signal

    result = await approve_signal(item_id)
    if not result.get("ok"):
        raise HTTPException(400, str(result.get("detail") or result.get("reasons") or "Rejected"))
    return result


@router.post("/approvals/{item_id}/reject")
async def approvals_reject(item_id: str, body: dict = Body(default={})) -> dict:
    from app.services.inbox import reject_signal

    reason = str(body.get("reason") or body.get("rejectionReason") or "")
    result = await reject_signal(item_id, reason)
    if not result.get("ok"):
        raise HTTPException(400, str(result.get("detail") or "Cannot reject"))
    return result


@router.get("/bot/status")
async def bot_status() -> dict:
    from app.services.trading_bot import get_coordinator
    from app.services.trading_bot.coordinator import today_signal_count
    from app.services.settings_store import load_runtime_settings

    runtime = await load_runtime_settings()
    snap = get_coordinator().snapshot()
    snap["enabled"] = bool(runtime.botEnabled)
    snap["paused"] = await is_paused()
    snap["signalsToday"] = await today_signal_count()
    return snap


@router.get("/bot/preflight")
async def bot_preflight() -> dict:
    from app.services.preflight import run_preflight

    return await run_preflight()


@router.post("/bot/start")
async def bot_start(force: bool = False) -> dict:
    from app.services.preflight import run_preflight
    from app.services.trading_bot import get_coordinator
    from app.services.settings_store import load_runtime_settings, save_runtime_settings

    report = await run_preflight()
    if report.get("blocking") and not force:
        raise HTTPException(409, detail={"preflight": report, "detail": "Preflight blocked start"})
    runtime = await load_runtime_settings()
    runtime.botEnabled = True
    await save_runtime_settings(runtime)
    if await is_paused():
        return {**get_coordinator().snapshot(), "enabled": True, "paused": True, "preflight": report}
    started = await get_coordinator().start()
    return {**started, "enabled": True, "paused": False, "preflight": report}


@router.post("/bot/stop")
async def bot_stop() -> dict:
    from app.services.trading_bot import get_coordinator
    from app.services.settings_store import load_runtime_settings, save_runtime_settings

    runtime = await load_runtime_settings()
    runtime.botEnabled = False
    await save_runtime_settings(runtime)
    return await get_coordinator().stop()


@router.get("/bot/signals")
async def bot_signals() -> dict:
    from app.services.trading_bot.store import list_signals

    return {"signals": await list_signals(50)}


@router.get("/bot/signals/{signal_id}")
async def bot_signal_get(signal_id: str) -> dict:
    from app.services.trading_bot.store import get_signal

    item = await get_signal(signal_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.patch("/bot/signals/{signal_id}")
async def bot_signal_patch(signal_id: str, patch: dict = Body(...)) -> dict:
    from app.services.trading_bot.store import update_signal
    from app.services.telegram_service import schedule_bot_result

    updated = await update_signal(signal_id, patch)
    if not updated:
        raise HTTPException(404, "Not found")
    if updated.get("status") in {"won", "lost"}:
        try:
            schedule_bot_result(updated, float(updated.get("pnl") or 0))
        except Exception:
            pass
    return updated


@router.post("/bot/signals/{signal_id}/to-recommendation")
async def bot_signal_promote(signal_id: str) -> dict:
    from app.services.trading_bot.promote import promote_signal
    from app.services.trading_bot.store import get_signal

    signal = await get_signal(signal_id)
    if not signal:
        raise HTTPException(404, "Not found")
    if float(signal.get("confidence") or 0) < 0.8:
        raise HTTPException(400, "Confidence must be above 0.8 to convert")
    result = await promote_signal(signal_id)
    if not result.get("ok"):
        raise HTTPException(400, str(result.get("detail") or result.get("reasons") or "Rejected"))
    return result


@router.get("/bot/performance")
async def bot_performance() -> dict:
    from app.services.trading_bot.store import list_performance

    return {"performance": await list_performance()}


@router.get("/bot/performance/{agent}")
async def bot_performance_agent(agent: str) -> dict:
    from app.services.trading_bot.store import list_performance

    return {"agent": agent, "performance": await list_performance(agent)}


@router.post("/backtest/run")
async def backtest_run(body: dict = Body(...)) -> dict:
    from app.services.backtest.engine import BacktestEngine
    from app.services.backtest.models import BacktestRunRequest

    req = BacktestRunRequest.model_validate(body)
    report = await BacktestEngine().run(
        timeframe=req.timeframe,
        strategy_id=req.strategyId,
        days=req.days,
        risk_percent=req.riskPercent,
        min_rr=req.minRr,
        persist=True,
    )
    return report.model_dump(mode="json")


@router.get("/backtest/reports")
async def backtest_reports() -> dict:
    from app.services.backtest.store import list_reports

    return {"reports": await list_reports(20)}


@router.get("/backtest/reports/{report_id}")
async def backtest_report_get(report_id: str) -> dict:
    from app.services.backtest.store import get_report

    item = await get_report(report_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item


def _strategy_result(result: dict, not_found: bool = False) -> dict:
    if result.get("ok"):
        return result
    code = 404 if not_found or "not found" in str(result.get("detail") or "").lower() else 400
    raise HTTPException(code, str(result.get("detail") or "Rejected"))


@router.get("/strategies/proposed")
async def strategies_proposed() -> dict:
    from app.services.trading_bot.strategy_library import get_library

    rows = await get_library().get_all()
    proposed = [r.model_dump(mode="json") | {"timeframe": r.timeframes} for r in rows if r.status == "draft"]
    return {"strategies": proposed}


@router.get("/strategies")
async def strategies_list(status: str | None = None) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    rows = await get_library().get_all()
    if status and status != "all":
        rows = [r for r in rows if r.status == status]
    return {"strategies": [r.model_dump(mode="json") | {"timeframe": r.timeframes} for r in rows]}


@router.post("/strategies")
async def strategies_create(body: dict = Body(...)) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    source = str(body.get("source") or "manual")
    if source not in {"manual", "claude_proposed"}:
        source = "manual"
    created_by = str(body.get("created_by") or body.get("createdBy") or "operator")
    return _strategy_result(await get_library().propose(body, source=source, created_by=created_by))


@router.get("/strategies/{strategy_id}")
async def strategies_get(strategy_id: str) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    rule = await get_library().get(strategy_id)
    if rule is None:
        raise HTTPException(404, "Strategy not found")
    return rule.model_dump(mode="json") | {"timeframe": rule.timeframes}


@router.patch("/strategies/{strategy_id}")
async def strategies_patch(strategy_id: str, body: dict = Body(...)) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    return _strategy_result(await get_library().patch(strategy_id, body))


@router.delete("/strategies/{strategy_id}")
async def strategies_delete(strategy_id: str) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    return _strategy_result(await get_library().delete(strategy_id))


@router.post("/strategies/{strategy_id}/validate")
async def strategies_validate(strategy_id: str, body: dict | None = Body(default=None)) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    payload = body or {}
    result = await get_library().validate(strategy_id, days=int(payload.get("days") or 730), auto_activate=False)
    if result.get("paused"):
        raise HTTPException(409, str(result.get("detail") or "FoxAgent is paused"))
    return _strategy_result(result)


@router.post("/strategies/{strategy_id}/approve")
async def strategies_approve(strategy_id: str) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    return _strategy_result(await get_library().approve(strategy_id))


@router.post("/strategies/{strategy_id}/reject")
async def strategies_reject(strategy_id: str, body: dict | None = Body(default=None)) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    reason = str((body or {}).get("reason") or (body or {}).get("rejection_reason") or "")
    return _strategy_result(await get_library().reject(strategy_id, reason))


@router.post("/strategies/{strategy_id}/pin")
async def strategies_pin(strategy_id: str) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    return _strategy_result(await get_library().pin(strategy_id, True))


@router.post("/strategies/{strategy_id}/unpin")
async def strategies_unpin(strategy_id: str) -> dict:
    from app.services.trading_bot.strategy_library import get_library

    return _strategy_result(await get_library().pin(strategy_id, False))


@router.get("/bots")
async def bots_room() -> dict:
    from app.services.settings_store import load_runtime_settings
    from app.services.trading_bot import get_coordinator
    from app.services.trading_bot.circuit import snapshot as circuit_snap
    from app.services.trading_bot.news_candle_agent import NewsCandleAgent

    runtime = await load_runtime_settings()
    agents = list(getattr(runtime, "botAgents", None) or ["multi_strategy", "pattern_notes", "news_candle"])
    news = await NewsCandleAgent().window_status()
    return {
        "running": get_coordinator().snapshot(),
        "enabled": bool(runtime.botEnabled),
        "paused": await is_paused(),
        "agents": agents,
        "circuits": await circuit_snap(),
        "news": news,
    }


@router.get("/bots/news")
async def bots_news() -> dict:
    from app.services.trading_bot.news_candle_agent import NewsCandleAgent

    return await NewsCandleAgent().window_status()


@router.get("/bot/scans")
async def bot_scans() -> dict:
    from app.services.trading_bot.scans import list_scans

    return {"scans": list_scans(40)}


@router.get("/bot/scans/{scan_id}")
async def bot_scan_get(scan_id: str) -> dict:
    from app.services.trading_bot.scans import get_scan

    item = get_scan(scan_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.post("/bot/strategies/{strategy_id}/halt")
async def bot_strategy_halt(strategy_id: str, body: dict | None = Body(default=None)) -> dict:
    from app.services.trading_bot.circuit import halt

    reason = str((body or {}).get("reason") or "operator halt")
    return {"ok": True, "circuit": await halt(strategy_id, reason)}


@router.post("/bot/strategies/{strategy_id}/resume")
async def bot_strategy_resume(strategy_id: str) -> dict:
    from app.services.trading_bot.circuit import resume_strategy

    return {"ok": True, "circuit": await resume_strategy(strategy_id)}


@router.get("/lab/leaderboard")
async def lab_leaderboard() -> dict:
    from app.services.trading_bot.strategy_library import get_library
    from app.services.backtest.store import list_reports

    reports = await list_reports(40)
    by_id: dict[str, dict] = {}
    for rep in reports:
        sid = str(rep.get("strategyId") or "")
        if sid and sid not in by_id:
            by_id[sid] = rep
    rows = []
    for rule in await get_library().get_all():
        rep = by_id.get(rule.id) or {}
        rows.append(
            {
                "id": rule.id,
                "name": rule.name,
                "status": rule.status,
                "pinned": rule.pinned,
                "winRate": rep.get("winRate"),
                "profitFactor": rep.get("profitFactor"),
                "maxDrawdownR": rep.get("maxDrawdownR"),
                "totalTrades": rep.get("totalTrades"),
                "validatedAt": rule.validated_at,
            }
        )
    rows.sort(key=lambda r: (-float(r.get("profitFactor") or 0), -float(r.get("winRate") or 0)))
    return {"leaderboard": rows}


@router.post("/lab/experiments")
async def lab_experiment_start(body: dict = Body(...)) -> dict:
    from app.services.trading_bot.experiment import start_experiment

    result = await start_experiment(body)
    if result.get("paused"):
        raise HTTPException(409, str(result.get("detail") or "paused"))
    return _strategy_result(result)


@router.get("/lab/jobs")
async def lab_jobs() -> dict:
    from app.services.trading_bot.experiment import list_jobs

    return {"jobs": list_jobs()}


@router.get("/lab/jobs/{job_id}")
async def lab_job_get(job_id: str) -> dict:
    from app.services.trading_bot.experiment import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Not found")
    return job


@router.get("/briefing")
async def briefing_get() -> dict:
    from app.services.briefing import build_briefing

    return await build_briefing()


@router.post("/telegram/commands")
async def telegram_commands(body: dict = Body(...)) -> dict:
    from app.services.telegram_ops import handle_command

    return await handle_command(str(body.get("text") or ""), str(body.get("chatId") or body.get("chat_id") or ""))


@router.get("/journal")
async def journal_list() -> dict:
    from app.services.journal import list_journal

    return {"entries": list_journal()}


@router.patch("/recommendations/{rec_id}/postmortem")
async def rec_postmortem(rec_id: str, body: dict = Body(...)) -> dict:
    from app.services.journal import write_postmortem

    result = await write_postmortem(rec_id, body)
    if not result.get("ok"):
        raise HTTPException(404, str(result.get("detail") or "Not found"))
    return result


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
