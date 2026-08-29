from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Awaitable

from app.config import get_settings
from app.db import save_recommendation
from app.services.telegram_service import schedule_trade_alert
from app.schemas import ChatRequest, TradeRecommendation, new_id
from app.services.analysis import analyze_structure, build_recommendation, structure_summary
from app.services.chart_capture import render_candles_b64
from app.services.mcp_tools import dispatch_tool, mcp_tool_specs, try_build_sdk_server
from app.services.oanda import oanda
from app.services.simulator import normalize_granularity
from app.services.settings_store import load_runtime_settings

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

PHASES = [
    {"id": 1, "name": "Fetching OANDA Candles (1D, 4H, 15M)", "detail": "Multi-timeframe OHLCV ingest"},
    {"id": 2, "name": "Visual Chart Inspection & Liquidity Mapping", "detail": "Claude Vision + ICT structure"},
    {"id": 3, "name": "Macro & Sentiment Ingestion", "detail": "Session liquidity, HTF bias, confluence"},
    {"id": 4, "name": "Synthesizing Recommendation & Chart Annotations", "detail": "Overlays, entry, SL, TP"},
]

MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-5",
    "sonnet-4": "claude-sonnet-4-5",
    "claude 3.7 sonnet": "claude-3-7-sonnet-latest",
    "claude-3.7-sonnet": "claude-3-7-sonnet-latest",
    "3.7": "claude-3-7-sonnet-latest",
    "claude 3.5 sonnet": "claude-3-5-sonnet-latest",
    "claude-3.5-sonnet": "claude-3-5-sonnet-latest",
    "haiku": "claude-3-5-haiku-latest",
    "claude 3.5 haiku": "claude-3-5-haiku-latest",
    "opus": "claude-opus-4-5",
}

SYSTEM_PROMPT = """You are FoxAgent, an elite ICT / Smart Money Concepts trading analyst working a live OANDA desk.

Multi-timeframe process (mandatory):
1. HTF (D / H4): trend, liquidity pools, MSS, order blocks.
2. MTF (H1 / M15): BOS, FVG, range equilibrium, Fibonacci 0.5 / 0.618 / 0.786.
3. LTF (M5 / M1): entry trigger, liquidity sweeps, confirmation candles.

Dual-pass:
- Call get_candles and structure_scan on HTF, MTF, and entry TF.
- Call capture_chart_screenshot for visual confirmation (head & shoulders, trendlines, S/R taps, false breakouts).
- Then synthesize ONE TradeRecommendation.

Output contract (final message MUST contain a single JSON object, no markdown fences):
{
  "id": "rec_...",
  "timestamp": "ISO-8601",
  "symbol": "XAU_USD",
  "timeframe": "15m",
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "tradeSetup": {
    "action": "BUY" | "SELL",
    "orderType": "LIMIT" | "STOP" | "MARKET",
    "entryPrice": 0,
    "stopLoss": 0,
    "takeProfitLevels": [{"level": 1, "price": 0, "ratio": "1:1.6"}, {"level": 2, "price": 0, "ratio": "1:3.0"}],
    "riskRewardRatio": 3.0
  },
  "rationale": "human-like mentor explanation",
  "confluence": ["..."],
  "klineOverlays": [
    {
      "name": "rect" | "trendLine" | "fibonacci" | "priceLine" | "textAnnotation",
      "groupId": "string",
      "points": [{"timestamp": 1710000000000, "value": 0.0}],
      "styles": {"fillColor": "rgba(34,197,94,0.2)", "borderColor": "#22c55e", "lineColor": "#eab308", "lineWidth": 2},
      "annotationText": "optional"
    }
  ],
  "focusTimestamp": 1710000000000
}

Overlay timestamps MUST be real candle timestamps in milliseconds from get_candles.
Respect minimum R:R of 1:2. Prefer LIMIT entries at FVG / OB equilibrium.
Call send_recommendation with the same JSON when complete.
"""


def resolve_model(name: str) -> str:
    key = name.strip().lower()
    return MODEL_ALIASES.get(key, name.strip() or "claude-sonnet-4-5")


def extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    blob = fence.group(1) if fence else None
    if blob is None:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            blob = text[start : end + 1]
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def _set_phase(emit: Emit, run_id: str, phase_id: int, status: str, detail: str = "") -> None:
    phase = next(p for p in PHASES if p["id"] == phase_id)
    await emit(
        "phase",
        {
            "runId": run_id,
            "phase": {**phase, "status": status, "detail": detail or phase["detail"]},
        },
    )


async def run_algorithmic(
    req: ChatRequest,
    emit: Emit,
    run_id: str,
    vision_notes: str | None = None,
) -> TradeRecommendation:
    gran = normalize_granularity(req.timeframe)
    await _set_phase(emit, run_id, 1, "active", "Pulling D / H4 / entry timeframe candles")
    await emit("thought", {"runId": run_id, "text": f"Fetching OANDA-style candles for {req.symbol}…"})
    daily = await oanda.get_candles(req.symbol, "D", 180)
    h4 = await oanda.get_candles(req.symbol, "H4", 240)
    ltf = await oanda.get_candles(req.symbol, gran, 400)
    await _set_phase(emit, run_id, 1, "complete")

    await _set_phase(emit, run_id, 2, "active", "Mapping FVG, OB, BOS and session liquidity")
    htf = analyze_structure(daily)
    mtf = analyze_structure(h4)
    ltf_report = analyze_structure(ltf)
    await emit(
        "thought",
        {
            "runId": run_id,
            "text": f"HTF bias {htf.bias}. H4 {mtf.bias}. {req.timeframe} {ltf_report.bias}.",
        },
    )
    snapshots = {
        "D": render_candles_b64(daily, f"{req.symbol} Daily"),
        "H4": render_candles_b64(h4, f"{req.symbol} H4"),
        gran: render_candles_b64(ltf, f"{req.symbol} {gran}"),
    }
    await emit("charts", {"runId": run_id, "timeframes": list(snapshots.keys())})
    await _set_phase(emit, run_id, 2, "complete")

    await _set_phase(emit, run_id, 3, "active", "Combining session liquidity with HTF narrative")
    await asyncio.sleep(0.15)
    await emit(
        "thought",
        {
            "runId": run_id,
            "text": "; ".join(ltf_report.confluence) or "Scanning confluence…",
        },
    )
    await _set_phase(emit, run_id, 3, "complete")

    await _set_phase(emit, run_id, 4, "active", "Drawing overlays and packaging the setup")
    rec = build_recommendation(
        symbol=req.symbol,
        timeframe=req.timeframe,
        candles=ltf,
        htf_bias=htf.bias if htf.bias != "NEUTRAL" else mtf.bias,
        model=req.model,
        vision_notes=vision_notes,
    )
    rec = rec.model_copy(update={"id": rec.id})
    await save_recommendation(rec)
    schedule_trade_alert(rec)
    await emit("recommendation", rec.model_dump(mode="json") | {"runId": run_id})
    await emit(
        "assistant",
        {
            "runId": run_id,
            "text": rec.rationale,
            "recommendationId": rec.id,
        },
    )
    await _set_phase(emit, run_id, 4, "complete")
    return rec


async def run_anthropic_loop(req: ChatRequest, emit: Emit, run_id: str) -> TradeRecommendation | None:
    runtime = await load_runtime_settings()
    api_key = runtime.anthropicApiKey or get_settings().anthropic_api_key
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    model = resolve_model(req.model or runtime.defaultClaudeModel)
    client = anthropic.AsyncAnthropic(api_key=api_key)
    tools = mcp_tool_specs()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Instrument {req.symbol}. Working timeframe {req.timeframe}. "
                f"User prompt: {req.message}\n"
                "Run the full MTF + vision process, then emit the recommendation JSON."
            ),
        }
    ]

    await _set_phase(emit, run_id, 1, "active")
    rec: TradeRecommendation | None = None

    for _turn in range(10):
        try:
            stream = await client.messages.create(
                model=model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
                stream=True,
            )
        except Exception as exc:
            logger.warning("Anthropic call failed: %s", exc)
            await emit("thought", {"runId": run_id, "text": f"Claude API error: {exc}"})
            return None

        text_acc = ""
        tool_uses: list[dict[str, Any]] = []
        async for event in stream:
            et = getattr(event, "type", "")
            if et == "content_block_delta":
                delta = event.delta
                if getattr(delta, "type", "") == "text_delta":
                    chunk = delta.text
                    text_acc += chunk
                    await emit("token", {"runId": run_id, "text": chunk})
                elif getattr(delta, "type", "") == "thinking_delta":
                    await emit("thought", {"runId": run_id, "text": getattr(delta, "thinking", "")})
            elif et == "content_block_start":
                block = event.content_block
                if getattr(block, "type", "") == "tool_use":
                    tool_uses.append({"id": block.id, "name": block.name, "input": dict(block.input or {})})
            elif et == "content_block_stop":
                pass
            elif et == "message_delta":
                pass

        # Non-stream fallback capture: if stream API shape differs, do a non-stream call
        if not text_acc and not tool_uses:
            try:
                msg = await client.messages.create(
                    model=model,
                    max_tokens=8000,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=messages,
                )
            except Exception as exc:
                logger.warning("Anthropic non-stream failed: %s", exc)
                return None
            tool_uses = []
            for block in msg.content:
                if block.type == "text":
                    text_acc += block.text
                    await emit("token", {"runId": run_id, "text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append({"id": block.id, "name": block.name, "input": dict(block.input)})
            stop_reason = msg.stop_reason
            assistant_content = [b.model_dump() for b in msg.content]
        else:
            stop_reason = "tool_use" if tool_uses else "end_turn"
            assistant_content = []
            if text_acc:
                assistant_content.append({"type": "text", "text": text_acc})
            assistant_content.extend(
                {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]} for t in tool_uses
            )

        parsed = extract_json_object(text_acc)
        if parsed and "tradeSetup" in parsed:
            try:
                rec = TradeRecommendation.model_validate(parsed)
            except Exception:
                rec = None

        if stop_reason != "tool_use" or not tool_uses:
            if rec:
                await save_recommendation(rec)
                schedule_trade_alert(rec)
                await emit("recommendation", rec.model_dump(mode="json") | {"runId": run_id})
            return rec

        # Execute tools
        tool_results = []
        for t in tool_uses:
            await emit("thought", {"runId": run_id, "text": f"Tool {t['name']}({json.dumps(t['input'])[:120]})"})
            if t["name"] == "get_candles":
                await _set_phase(emit, run_id, 1, "active", f"{t['input']}")
            if t["name"] == "capture_chart_screenshot":
                await _set_phase(emit, run_id, 2, "active")
            if t["name"] == "send_recommendation":
                await _set_phase(emit, run_id, 4, "active")
            try:
                result = await dispatch_tool(t["name"], t["input"], emit)
                if t["name"] == "capture_chart_screenshot":
                    content: Any = [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": result},
                        }
                    ]
                else:
                    content = json.dumps(result, default=str)[:20000]
                if t["name"] == "send_recommendation" and isinstance(result, bool):
                    await _set_phase(emit, run_id, 4, "complete")
            except Exception as exc:
                content = f"error: {exc}"
            tool_results.append(
                {"type": "tool_result", "tool_use_id": t["id"], "content": content}
            )

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
        await _set_phase(emit, run_id, 1, "complete")

    return rec


async def run_claude_agent_sdk(req: ChatRequest, emit: Emit, run_id: str) -> TradeRecommendation | None:
    runtime = await load_runtime_settings()
    api_key = runtime.anthropicApiKey or get_settings().anthropic_api_key
    if not api_key:
        return None
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    except Exception:
        return None

    server = try_build_sdk_server()
    if server is None:
        return None

    model = resolve_model(req.model or runtime.defaultClaudeModel)
    options = ClaudeAgentOptions(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"oanda": server},
        allowed_tools=[
            "mcp__oanda__get_candles",
            "mcp__oanda__get_live_price",
            "mcp__oanda__capture_chart_screenshot",
            "mcp__oanda__structure_scan",
            "mcp__oanda__send_recommendation",
        ],
        permission_mode="acceptEdits",
        env={"ANTHROPIC_API_KEY": api_key},
        max_turns=12,
    )
    text_acc = ""
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(
                f"Instrument {req.symbol}. Timeframe {req.timeframe}. User: {req.message}"
            )
            async for msg in client.receive_response():
                msg_type = type(msg).__name__
                content = getattr(msg, "content", None)
                if isinstance(content, list):
                    for block in content:
                        btype = getattr(block, "type", "") or type(block).__name__
                        if "Thinking" in str(btype) or btype == "thinking":
                            await emit("thought", {"runId": run_id, "text": getattr(block, "thinking", str(block))})
                        elif hasattr(block, "text"):
                            text_acc += block.text
                            await emit("token", {"runId": run_id, "text": block.text})
                        elif "ToolUse" in str(type(block).__name__):
                            await emit(
                                "thought",
                                {"runId": run_id, "text": f"SDK tool {getattr(block, 'name', '')}"},
                            )
                elif msg_type == "ResultMessage":
                    break
    except Exception as exc:
        logger.warning("Claude Agent SDK failed, falling back: %s", exc)
        await emit("thought", {"runId": run_id, "text": f"Agent SDK unavailable ({exc}). Falling back."})
        return None

    parsed = extract_json_object(text_acc)
    if parsed and "tradeSetup" in parsed:
        rec = TradeRecommendation.model_validate(parsed)
        await save_recommendation(rec)
        schedule_trade_alert(rec)
        await emit("recommendation", rec.model_dump(mode="json") | {"runId": run_id})
        return rec
    return None


async def run_chat(req: ChatRequest, emit: Emit) -> dict[str, Any]:
    run_id = new_id("run")
    await emit("run_start", {"runId": run_id, "symbol": req.symbol, "model": req.model, "phases": PHASES})
    rec: TradeRecommendation | None = None
    engine = "algorithmic"

    runtime = await load_runtime_settings()
    if runtime.anthropicApiKey or get_settings().anthropic_api_key:
        rec = await run_claude_agent_sdk(req, emit, run_id)
        if rec:
            engine = "claude-agent-sdk"
        else:
            rec = await run_anthropic_loop(req, emit, run_id)
            if rec:
                engine = "anthropic-tools"

    if rec is None:
        rec = await run_algorithmic(req, emit, run_id)
        engine = "algorithmic+vision-render"

    await emit(
        "run_complete",
        {"runId": run_id, "engine": engine, "recommendationId": rec.id if rec else None},
    )
    return {"runId": run_id, "engine": engine, "recommendation": rec.model_dump(mode="json") if rec else None}
