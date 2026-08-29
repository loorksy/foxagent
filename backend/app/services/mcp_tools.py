from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from app.services.analysis import analyze_structure, structure_summary
from app.services.chart_capture import render_candles_b64
from app.services.oanda import oanda
from app.db import save_recommendation
from app.schemas import KlineOverlay, TradeRecommendation
from app.services.telegram_service import schedule_trade_alert

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


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


async def tool_send_recommendation(payload: dict[str, Any], emit: Emit | None = None) -> bool:
    rec = TradeRecommendation.model_validate(payload)
    await save_recommendation(rec)
    schedule_trade_alert(rec)
    if emit:
        await emit("recommendation", rec.model_dump(mode="json"))
    return True


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
            "description": "Render a dark candlestick chart snapshot (optional klineOverlays drawn first) and return a base64 PNG.",
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
        ok = await tool_send_recommendation(args.get("payload") or args)
        return {"content": [{"type": "text", "text": json.dumps({"ok": ok})}]}

    return create_sdk_mcp_server(
        name="oanda",
        version="1.0.0",
        tools=[
            get_candles,
            get_live_price,
            capture_chart_screenshot,
            structure_scan,
            send_recommendation,
        ],
    )
