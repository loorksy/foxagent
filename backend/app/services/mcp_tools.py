from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Callable, Awaitable

from app.services.analysis import analyze_structure, calculate_ict_levels, structure_summary
from app.services.chart_capture import render_candles_b64
from app.services.chart_shots import save_chart_shot
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


def compact_tool_output(name: str, out: Any) -> Any:
    if name == "capture_chart_screenshot" and isinstance(out, str):
        return {"image": "png", "bytes": len(out)}
    if isinstance(out, dict):
        public = {k: v for k, v in out.items() if k != "image"}
        if "image" in out:
            public["image"] = "png"
        return public
    if isinstance(out, str):
        return {"text": out[:400]}
    return out


async def publish_chart_image(emit: Emit | None, b64: str, title: str = "") -> dict[str, str] | None:
    sink = emit or _current_emit.get()
    shot = save_chart_shot(b64)
    if not shot:
        return None
    payload = {"id": shot["id"], "url": shot["url"], "kind": "chart"}
    if title:
        payload["title"] = title
    if sink:
        await sink("agent_image", payload)
    return shot


async def emit_tool_result(
    name: str,
    out: Any,
    emit: Emit | None = None,
    tool_id: str = "",
    agent: str = "",
) -> None:
    sink = emit or _current_emit.get()
    if not sink:
        return
    await sink(
        "agent_tool_result",
        {
            "name": name,
            "id": tool_id,
            "agent": agent,
            "output": compact_tool_output(name, out),
        },
    )
    image = None
    if name == "capture_chart_screenshot" and isinstance(out, str):
        image = out
    elif isinstance(out, dict) and isinstance(out.get("image"), str) and len(out["image"]) > 80:
        image = out["image"]
    if image:
        await publish_chart_image(sink, image, title=name)


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


async def tool_get_economic_calendar(
    instrument: str = "XAU_USD",
    hours_ahead: int = 24,
    min_impact: str = "medium",
) -> dict[str, Any]:
    """جلسة UTC + أحداث USD الحقيقية المؤثرة على الذهب. لا يختلق طبعات."""
    session = await get_economic_calendar(instrument)
    from app.services.economic_calendar import upcoming_events

    live = await upcoming_events(hours_ahead=hours_ahead, min_impact=min_impact)
    events = live.get("events") or []
    payload = {
        **session,
        "events": events,
        "cached": bool(live.get("cached")),
        "hoursAhead": hours_ahead,
        "minImpact": min_impact,
        "instrument": instrument or "XAU_USD",
    }
    if events:
        payload["source"] = live.get("source") or "forex_factory"
        payload["note"] = "Real USD events that typically move XAU_USD. Empty actuals mean the print is still pending."
    if live.get("warning"):
        payload["warning"] = live["warning"]
    return payload


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


async def tool_propose_strategy(payload: dict[str, Any] | None = None, emit: Emit | None = None) -> dict[str, Any]:
    """اقتراح استراتيجية ذهب جديدة — تُحفظ كمسودة."""
    from app.services.trading_bot.strategy_library import get_library

    body = dict(payload or {})
    result = await get_library().propose(body, source="claude_proposed", created_by="claude")
    if result.get("ok"):
        sink = emit or _current_emit.get()
        if sink:
            await sink("strategy_proposal", result.get("strategy") or {})
    return result


async def tool_experiment_strategy(payload: dict[str, Any] | None = None, emit: Emit | None = None) -> dict[str, Any]:
    from app.services.trading_bot.experiment import start_experiment

    result = await start_experiment(dict(payload or {}))
    sink = emit or _current_emit.get()
    if sink:
        await sink("strategy_experiment", result.get("job") or {})
    return result


async def tool_validate_strategy(strategy_id: str, emit: Emit | None = None) -> dict[str, Any]:
    """تشغيل باك تست على استراتيجية مقترحة واعتمادها إن تجاوزت الحدود."""
    from app.services.trading_bot.strategy_library import get_library

    result = await get_library().validate(strategy_id, days=730, auto_activate=False)
    sink = emit or _current_emit.get()
    if sink:
        await sink("strategy_validation", {k: result.get(k) for k in ("ok", "passed", "reasons", "strategy")})
    return result


async def tool_list_strategies(status: str = "active") -> dict[str, Any]:
    from app.services.trading_bot.strategy_library import get_library

    rows = await get_library().get_all()
    if status and status != "all":
        rows = [r for r in rows if r.status == status]
    return {"strategies": [r.model_dump(mode="json") for r in rows]}


async def tool_draw_on_chart(
    overlays: list[dict[str, Any]] | None,
    emit: Emit | None = None,
    instrument: str = "XAU_USD",
    granularity: str = "M15",
) -> dict[str, Any]:
    """Emit additive chart overlays and return an annotated PNG so the model can see them."""
    parsed_models: list[KlineOverlay] = []
    parsed: list[dict[str, Any]] = []
    for item in overlays or []:
        try:
            model = KlineOverlay.model_validate(item)
            parsed_models.append(model)
            parsed.append(model.model_dump(mode="json"))
        except Exception:
            continue
    payload = {"overlays": parsed, "additive": True}
    sink = emit or _current_emit.get()
    if sink:
        await sink("agent_chart_overlays", payload)
    image_b64 = ""
    try:
        candles = await oanda.get_candles(instrument or "XAU_USD", granularity or "M15", 180)
        image_b64 = render_candles_b64(candles, f"{instrument} {granularity} annotated", parsed_models or None)
        await publish_chart_image(sink, image_b64, title="drawing")
    except Exception:
        image_b64 = ""
    result: dict[str, Any] = {"ok": True, **payload, "preview": "annotated chart attached"}
    if image_b64:
        result["image"] = image_b64
    return result


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
            "description": "UTC session clock plus real USD events that typically move gold. Does not invent prints if the feed is empty.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "hours_ahead": {"type": "integer", "minimum": 1, "maximum": 168},
                    "min_impact": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                },
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
                    },
                    "instrument": {"type": "string"},
                    "granularity": {"type": "string"},
                },
                "required": ["overlays"],
            },
        },
        {
            "name": "propose_strategy",
            "description": "Propose a new XAU_USD strategy as a draft. Gold only. Operator must validate via backtest.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "timeframes": {"type": "array", "items": {"type": "string"}},
                    "direction": {"type": "string", "enum": ["buy", "sell", "both"]},
                    "entry_conditions": {"type": "object"},
                    "sessions": {"type": "array", "items": {"type": "string"}},
                    "dsl": {"type": "object"},
                    "kind": {"type": "string", "enum": ["dsl", "python"], "description": "dsl (default) or python code strategy"},
                    "code": {"type": "string", "description": "Python code defining on_bar(ctx) — required when kind=python"},
                    "stop_rule": {"type": "string"},
                    "tp1_r": {"type": "number"},
                    "tp2_r": {"type": "number"},
                    "max_holding_bars": {"type": "integer"},
                },
                "required": ["name"],
            },
        },
        {
            "name": "validate_strategy",
            "description": "Run the warehouse backtest on a drafted gold strategy. Never pins it — the operator must approve.",
            "input_schema": {
                "type": "object",
                "properties": {"strategy_id": {"type": "string"}},
                "required": ["strategy_id"],
            },
        },
        {
            "name": "experiment_strategy",
            "description": "Propose a gold strategy draft and run up to 8 warehouse backtests. Never pins. Operator must approve.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "timeframes": {"type": "array", "items": {"type": "string"}},
                    "direction": {"type": "string", "enum": ["buy", "sell", "both"]},
                    "entry_conditions": {"type": "object"},
                    "sessions": {"type": "array", "items": {"type": "string"}},
                    "dsl": {"type": "object"},
                    "stop_rule": {"type": "string"},
                    "tp1_r": {"type": "number"},
                    "tp2_r": {"type": "number"},
                    "max_holding_bars": {"type": "integer"},
                    "days": {"type": "integer"},
                },
            },
        },
        {
            "name": "list_strategies",
            "description": "List gold strategies in the library (active, draft, rejected, or all).",
            "input_schema": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
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


async def dispatch_tool(
    name: str,
    args: dict[str, Any],
    emit: Emit | None = None,
    tool_id: str = "",
    agent: str = "",
) -> Any:
    if name == "get_candles":
        out: Any = await tool_get_candles(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 300),
        )
    elif name == "get_live_price":
        out = await tool_get_live_price(args["instrument"])
    elif name == "capture_chart_screenshot":
        out = await tool_capture_chart_screenshot(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 180),
            args.get("overlays"),
        )
    elif name == "structure_scan":
        out = await tool_structure_scan(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 300),
        )
    elif name == "send_recommendation":
        payload = args.get("payload") or args
        out = await tool_send_recommendation(payload, emit)
    elif name == "calculate_ict_levels":
        out = await tool_calculate_ict_levels(
            args["instrument"],
            args["granularity"],
            int(args.get("count") or 300),
        )
    elif name == "query_technical_memory":
        out = await tool_query_technical_memory(args["instrument"], args.get("query") or "")
    elif name == "query_macro_memory":
        out = await tool_query_macro_memory(args["instrument"], args.get("query") or "")
    elif name == "get_economic_calendar":
        out = await tool_get_economic_calendar(
            args.get("instrument") or "XAU_USD",
            int(args.get("hours_ahead") or 24),
            str(args.get("min_impact") or "medium"),
        )
    elif name == "get_market_sentiment":
        out = await get_market_sentiment(args.get("instrument") or "XAU_USD")
    elif name == "fetch_financial_news":
        out = await fetch_financial_news(args.get("instrument") or "XAU_USD")
    elif name == "validate_risk_rules":
        out = await validate_risk_rules(args.get("payload") or args)
    elif name == "record_post_trade_reflection":
        out = await tool_record_post_trade_reflection(
            args["recommendation_id"],
            args["outcome"],
            float(args.get("pnl") or 0.0),
        )
    elif name == "draw_on_chart":
        out = await tool_draw_on_chart(
            args.get("overlays") or [],
            emit,
            str(args.get("instrument") or "XAU_USD"),
            str(args.get("granularity") or "M15"),
        )
    elif name == "propose_strategy":
        out = await tool_propose_strategy(args, emit)
    elif name == "validate_strategy":
        out = await tool_validate_strategy(
            str(args.get("strategy_id") or args.get("strategyId") or args.get("id") or ""),
            emit,
        )
    elif name == "list_strategies":
        out = await tool_list_strategies(str(args.get("status") or "active"))
    elif name == "experiment_strategy":
        out = await tool_experiment_strategy(args, emit)
    else:
        raise ValueError(f"Unknown tool: {name}")
    await emit_tool_result(name, out, emit=emit, tool_id=tool_id, agent=agent)
    return out


async def _sdk_payload(name: str, args: dict[str, Any]) -> dict[str, Any]:
    data = await dispatch_tool(name, args)
    public = compact_tool_output(name, data)
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(public, default=str)}]
    image = None
    if name == "capture_chart_screenshot" and isinstance(data, str):
        image = data
    elif isinstance(data, dict) and isinstance(data.get("image"), str) and len(data["image"]) > 80:
        image = data["image"]
    if image:
        content.insert(0, {"type": "image", "data": image, "mimeType": "image/png"})
    return {"content": content}


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
        return await _sdk_payload("get_candles", args)

    @tool("get_live_price", "Get live bid/ask/mid.", {"instrument": str})
    async def get_live_price(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("get_live_price", args)

    @tool(
        "capture_chart_screenshot",
        "Render chart snapshot as base64 PNG.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def capture_chart_screenshot(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("capture_chart_screenshot", args)

    @tool(
        "structure_scan",
        "Algorithmic ICT structure scan.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def structure_scan(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("structure_scan", args)

    @tool("send_recommendation", "Save a trade recommendation overlay payload.", {"payload": dict})
    async def send_recommendation(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("send_recommendation", args)

    @tool(
        "calculate_ict_levels",
        "Map FVGs, order blocks, session liquidity.",
        {"instrument": str, "granularity": str, "count": int},
    )
    async def calculate_ict_levels_tool(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("calculate_ict_levels", args)

    @tool("query_technical_memory", "Recall technical lessons.", {"instrument": str, "query": str})
    async def query_technical_memory(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("query_technical_memory", args)

    @tool(
        "get_economic_calendar",
        "UTC session clock plus real USD gold events.",
        {"instrument": str, "hours_ahead": int, "min_impact": str},
    )
    async def economic_calendar(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("get_economic_calendar", args)

    @tool("get_market_sentiment", "Live bias and session.", {"instrument": str})
    async def market_sentiment(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("get_market_sentiment", args)

    @tool("fetch_financial_news", "Reuters business headlines.", {"instrument": str})
    async def financial_news(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("fetch_financial_news", args)

    @tool("query_macro_memory", "Recall macro lessons.", {"instrument": str, "query": str})
    async def query_macro_memory(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("query_macro_memory", args)

    @tool("validate_risk_rules", "Enforce R:R and session gates.", {"payload": dict})
    async def validate_risk(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("validate_risk_rules", args)

    @tool(
        "draw_on_chart",
        "Draw additive ICT overlays on the live chart during analysis.",
        {"overlays": list},
    )
    async def draw_on_chart(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("draw_on_chart", args)

    @tool(
        "record_post_trade_reflection",
        "Write a lesson after TP/SL/expire.",
        {"recommendation_id": str, "outcome": str, "pnl": float},
    )
    async def record_reflection(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("record_post_trade_reflection", args)

    @tool(
        "propose_strategy",
        "Propose a new XAU_USD strategy draft. Gold only.",
        {
            "name": str,
            "description": str,
            "kind": str,
            "code": str,
            "timeframes": list,
            "direction": str,
            "entry_conditions": dict,
            "stop_rule": str,
            "tp1_r": float,
            "tp2_r": float,
            "max_holding_bars": int,
        },
    )
    async def propose_strategy(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("propose_strategy", args)

    @tool("validate_strategy", "Backtest a drafted gold strategy on the warehouse.", {"strategy_id": str})
    async def validate_strategy(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("validate_strategy", args)

    @tool("list_strategies", "List gold strategies in the library.", {"status": str})
    async def list_strategies(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("list_strategies", args)

    @tool(
        "experiment_strategy",
        "Draft a gold strategy and run up to 8 warehouse backtests. Never pins.",
        {
            "name": str,
            "description": str,
            "timeframes": list,
            "direction": str,
            "entry_conditions": dict,
            "sessions": list,
            "dsl": dict,
            "stop_rule": str,
            "tp1_r": float,
            "tp2_r": float,
            "max_holding_bars": int,
            "days": int,
        },
    )
    async def experiment_strategy(args: dict[str, Any]) -> dict[str, Any]:
        return await _sdk_payload("experiment_strategy", args)

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
            propose_strategy,
            validate_strategy,
            list_strategies,
            experiment_strategy,
        ],
    )
