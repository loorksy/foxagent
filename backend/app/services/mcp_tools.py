from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Callable, Awaitable

from app.services.analysis import analyze_structure, calculate_ict_levels, structure_summary
from app.services.chart_capture import render_candles_b64
from app.services.macro_feed import fetch_financial_news, get_economic_calendar, get_market_sentiment
from app.services.memory_log import get_past_context
from app.services.oanda import oanda
from app.db import save_recommendation
from app.schemas import KlineOverlay, TradeRecommendation
from app.services.reflection import write_reflection
from app.services.risk_rules import RiskRejected, enforce_risk_gate, validate_risk_rules
from app.services.telegram_service import schedule_trade_alert

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
_current_emit: ContextVar[Emit | None] = ContextVar("foxagent_emit", default=None)


def set_tool_emit(emit: Emit | None):
    return _current_emit.set(emit)


def reset_tool_emit(token) -> None:
    _current_emit.reset(token)


async def tool_get_candles(instrument: str, granularity: str, count: int = 300) -> list[dict[str, Any]]:
    candles = await oanda.get_candles(instrument, granularity, count)
    return [c.to_kline() | {"time": c.time.isoformat(), "complete": c.complete} for c in candles]


async def tool_get_live_price(instrument: str) -> dict[str, Any]:
    px = await oanda.get_live_price(instrument)
    return px.model_dump(mode="json")


async def tool_capture_chart_screenshot(
    instrument: str,
    granularity: str,
    count: int = 180,
    overlays: list[dict] | None = None,
) -> str:
    candles = await oanda.get_candles(instrument, granularity, count)
    parsed: list[KlineOverlay] = []
    for item in overlays or []:
        try:
            parsed.append(KlineOverlay.model_validate(item))
        except Exception:
            continue
    return render_candles_b64(candles, f"{instrument} {granularity}", parsed or None)


async def tool_structure_scan(instrument: str, granularity: str, count: int = 300) -> dict[str, Any]:
    candles = await oanda.get_candles(instrument, granularity, count)
    report = analyze_structure(candles)
    return structure_summary(report)


async def tool_calculate_ict_levels(instrument: str, granularity: str, count: int = 300) -> dict[str, Any]:
    candles = await oanda.get_candles(instrument, granularity, count)
    return calculate_ict_levels(candles)


async def tool_query_technical_memory(instrument: str, query: str = "") -> dict[str, Any]:
    text = await get_past_context(instrument, query=query or f"{instrument} ICT FVG order block")
    return {"kind": "technical", "instrument": instrument, "context": text}


async def tool_query_macro_memory(instrument: str, query: str = "") -> dict[str, Any]:
    text = await get_past_context(instrument, query=query or f"{instrument} session calendar sentiment")
    return {"kind": "macro", "instrument": instrument, "context": text}


async def tool_record_post_trade_reflection(
    recommendation_id: str,
    outcome: str,
    pnl: float = 0.0,
) -> dict[str, Any]:
    result = await write_reflection(recommendation_id, outcome, pnl)
    return result or {"ok": False, "detail": "No pending memory entry for this recommendation"}


async def persist_recommendation(payload: dict[str, Any] | TradeRecommendation, emit: Emit | None = None) -> dict[str, Any]:
    """Validate risk rules then write. The LLM cannot skip this by omitting a tool call."""
    rec = payload if isinstance(payload, TradeRecommendation) else TradeRecommendation.model_validate(payload)
    dumped = rec.model_dump(mode="json")
    await enforce_risk_gate(dumped)
    await save_recommendation(rec)
    schedule_trade_alert(rec)
    if emit:
        await emit("recommendation", dumped)
        await emit("agent_recommendation", dumped)
    return {"ok": True, "recommendation": dumped}


async def tool_draw_on_chart(overlays: list[dict[str, Any]] | None, emit: Emit | None = None) -> dict[str, Any]:
    """Emit additive chart overlays the model chose during analysis."""
    parsed: list[dict[str, Any]] = []
    for item in overlays or []:
        try:
            parsed.append(KlineOverlay.model_validate(item).model_dump(mode="json"))
        except Exception:
            continue
    payload = {"overlays": parsed, "additive": True}
    sink = emit or _current_emit.get()
    if sink:
        await sink("agent_chart_overlays", payload)
    return {"ok": True, **payload}


async def tool_send_recommendation(payload: dict[str, Any], emit: Emit | None = None) -> dict[str, Any]:
    try:
        return await persist_recommendation(payload, emit)
    except RiskRejected as exc:
        return {"ok": False, "rejected": True, "reasons": exc.result.get("reasons"), "gate": exc.result}


def mcp_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_candles",
            "description": "Fetch OHLCV candles from OANDA (or the market simulator). granularity is OANDA format: M1, M5, M15, M30, H1, H4, D.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string", "description": "e.g. XAU_USD"},
                    "granularity": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1, "maximum": 5000},
                },
                "required": ["instrument", "granularity"],
            },
        },
        {
            "name": "get_live_price",
            "description": "Get the current bid/ask/mid for an instrument.",
            "input_schema": {
                "type": "object",
                "properties": {"instrument": {"type": "string"}},
                "required": ["instrument"],
            },
        },
        {
            "name": "capture_chart_screenshot",
            "description": "Required for full analysis if no chart image is already attached. Render a dark candlestick chart snapshot (optional klineOverlays drawn first) and return a base64 PNG.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "granularity": {"type": "string"},
                    "count": {"type": "integer"},
                    "overlays": {
                        "type": "array",
                        "description": "klineOverlays JSON (rect, trendLine, fibonacci, priceLine, textAnnotation)",
                    },
                },
                "required": ["instrument", "granularity"],
            },
        },
        {
            "name": "structure_scan",
            "description": "Run algorithmic ICT scan: FVG, order blocks, BOS, session liquidity, confluence.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "granularity": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["instrument", "granularity"],
            },
        },
        {
            "name": "send_recommendation",
            "description": "Persist and broadcast a TradeRecommendation JSON matching the overlay contract.",
            "input_schema": {
                "type": "object",
                "properties": {"payload": {"type": "object"}},
                "required": ["payload"],
            },
        },
        {
            "name": "calculate_ict_levels",
            "description": "Map FVGs, order blocks, session liquidity, swings, and Fibonacci of the last ICT structure scan.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "granularity": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["instrument", "granularity"],
            },
        },
        {
            "name": "query_technical_memory",
            "description": "Recall past technical decisions and post-trade lessons for this instrument.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["instrument"],
            },
        },
        {
            "name": "get_economic_calendar",
            "description": "UTC session clock and calendar windows. Does not invent economic prints.",
            "input_schema": {
                "type": "object",
                "properties": {"instrument": {"type": "string"}},
            },
        },
        {
            "name": "get_market_sentiment",
            "description": "Live mid/spread plus algorithmic HTF bias and liquidity sweep from OANDA candles.",
            "input_schema": {
                "type": "object",
                "properties": {"instrument": {"type": "string"}},
            },
        },
        {
            "name": "fetch_financial_news",
            "description": "Recent Reuters business headlines. Returns an honest failure if the feed is down.",
            "input_schema": {
                "type": "object",
                "properties": {"instrument": {"type": "string"}},
            },
        },
        {
            "name": "query_macro_memory",
            "description": "Recall past macro / session lessons for this instrument.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["instrument"],
            },
        },
        {
            "name": "validate_risk_rules",
            "description": "Check R:R floor, max risk %, and allowed sessions before approving a setup.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "payload": {"type": "object"},
                    "tradeSetup": {"type": "object"},
                    "entryPrice": {"type": "number"},
                    "stopLoss": {"type": "number"},
                    "riskRewardRatio": {"type": "number"},
                    "takeProfitLevels": {"type": "array"},
                },
            },
        },
        {
            "name": "draw_on_chart",
            "description": "Draw ICT structure on the live chart during analysis (FVG rects, liquidity lines, annotations). Additive — does not replace the final recommendation overlays.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "overlays": {
                        "type": "array",
                        "description": "klineOverlays: rect, trendLine, fibonacci, priceLine, textAnnotation",
                    }
                },
                "required": ["overlays"],
            },
        },
        {
            "name": "record_post_trade_reflection",
            "description": "Write a lesson-learned against a closed recommendation (TP / SL / expire).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "recommendation_id": {"type": "string"},
                    "outcome": {"type": "string"},
                    "pnl": {"type": "number"},
                },
                "required": ["recommendation_id", "outcome"],
            },
        },
    ]


async def dispatch_tool(name: str, args: dict[str, Any], emit: Emit | None = None) -> Any:
    if name == "get_candles":
        return await tool_get_candles(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 300),
        )
    if name == "get_live_price":
        return await tool_get_live_price(args["instrument"])
    if name == "capture_chart_screenshot":
        return await tool_capture_chart_screenshot(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 180),
            args.get("overlays"),
        )
    if name == "structure_scan":
        return await tool_structure_scan(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 300),
        )
    if name == "send_recommendation":
        payload = args.get("payload") or args
        return await tool_send_recommendation(payload, emit)
    if name == "calculate_ict_levels":
        return await tool_calculate_ict_levels(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 300),
        )
    if name == "query_technical_memory":
        return await tool_query_technical_memory(args["instrument"], args.get("query") or "")
    if name == "query_macro_memory":
        return await tool_query_macro_memory(args["instrument"], args.get("query") or "")
    if name == "get_economic_calendar":
        return await get_economic_calendar(args.get("instrument") or "XAU_USD")
    if name == "get_market_sentiment":
        return await get_market_sentiment(args.get("instrument") or "XAU_USD")
    if name == "fetch_financial_news":
        return await fetch_financial_news(args.get("instrument") or "XAU_USD")
    if name == "validate_risk_rules":
        return await validate_risk_rules(args.get("payload") or args)
    if name == "record_post_trade_reflection":
        return await tool_record_post_trade_reflection(
            args["recommendation_id"],
            args["outcome"],
            float(args.get("pnl") or 0.0),
        )
    if name == "draw_on_chart":
        return await tool_draw_on_chart(args.get("overlays") or [], emit)
    raise ValueError(f"Unknown tool: {name}")


def try_build_sdk_server():
    """Register FastMCP-style tools on Claude Agent SDK when available."""
    try:
        from claude_agent_sdk import tool, create_sdk_mcp_server
    except Exception:
        return None

    @tool(
        "get_candles",
        "Fetch OHLCV candles from OANDA REST / simulator.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def get_candles(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_get_candles(
            args["instrument"], args["granularity"], int(args.get("count") or 300)
        )
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool("get_live_price", "Get live bid/ask/mid.", {"instrument": str})
    async def get_live_price(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_get_live_price(args["instrument"])
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool(
        "capture_chart_screenshot",
        "Render chart snapshot as base64 PNG.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def capture_chart_screenshot(args: dict[str, Any]) -> dict[str, Any]:
        b64 = await tool_capture_chart_screenshot(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 180),
            args.get("overlays"),
        )
        return {
            "content": [
                {"type": "image", "data": b64, "mimeType": "image/png"},
                {"type": "text", "text": "Chart snapshot captured."},
            ]
        }

    @tool(
        "structure_scan",
        "Algorithmic ICT structure scan.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def structure_scan(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_structure_scan(
            args["instrument"], args["granularity"], int(args.get("count") or 300)
        )
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool("send_recommendation", "Save a trade recommendation overlay payload.", {"payload": dict})
    async def send_recommendation(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_send_recommendation(args.get("payload") or args)
        return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

    @tool(
        "calculate_ict_levels",
        "Map FVGs, order blocks, session liquidity.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def calculate_ict_levels_tool(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_calculate_ict_levels(
            args["instrument"], args["granularity"], int(args.get("count") or 300)
        )
        return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

    @tool("query_technical_memory", "Recall technical lessons.", {"instrument": str, "query": str})
    async def query_technical_memory(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_query_technical_memory(args["instrument"], args.get("query") or "")
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool("get_economic_calendar", "UTC session clock.", {"instrument": str})
    async def economic_calendar(args: dict[str, Any]) -> dict[str, Any]:
        data = await get_economic_calendar(args.get("instrument") or "XAU_USD")
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool("get_market_sentiment", "Live bias and session.", {"instrument": str})
    async def market_sentiment(args: dict[str, Any]) -> dict[str, Any]:
        data = await get_market_sentiment(args.get("instrument") or "XAU_USD")
        return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

    @tool("fetch_financial_news", "Reuters business headlines.", {"instrument": str})
    async def financial_news(args: dict[str, Any]) -> dict[str, Any]:
        data = await fetch_financial_news(args.get("instrument") or "XAU_USD")
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool("query_macro_memory", "Recall macro lessons.", {"instrument": str, "query": str})
    async def query_macro_memory(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_query_macro_memory(args["instrument"], args.get("query") or "")
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    @tool("validate_risk_rules", "Enforce R:R and session gates.", {"payload": dict})
    async def validate_risk(args: dict[str, Any]) -> dict[str, Any]:
        data = await validate_risk_rules(args.get("payload") or args)
        return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

    @tool(
        "draw_on_chart",
        "Draw additive ICT overlays on the live chart during analysis.",
        {"overlays": list},
    )
    async def draw_on_chart(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_draw_on_chart(args.get("overlays") or [], None)
        return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

    @tool(
        "record_post_trade_reflection",
        "Write a lesson after TP/SL/expire.",
        {"recommendation_id": str, "outcome": str, "pnl": float},
    )
    async def record_reflection(args: dict[str, Any]) -> dict[str, Any]:
        data = await tool_record_post_trade_reflection(
            args["recommendation_id"], args["outcome"], float(args.get("pnl") or 0.0)
        )
        return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

    return create_sdk_mcp_server(
        name="oanda",
        version="1.0.0",
        tools=[
            get_candles,
            get_live_price,
            capture_chart_screenshot,
            structure_scan,
            send_recommendation,
            calculate_ict_levels_tool,
            query_technical_memory,
            economic_calendar,
            market_sentiment,
            financial_news,
            query_macro_memory,
            validate_risk,
            record_reflection,
            draw_on_chart,
        ],
    )
