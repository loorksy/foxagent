from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Awaitable

from app.db import save_recommendation
from app.services.telegram_service import schedule_trade_alert
from app.schemas import ChatRequest, TradeRecommendation, new_id
from app.services.mcp_tools import dispatch_tool, mcp_tool_specs, try_build_sdk_server
from app.services.settings_store import load_runtime_settings, resolve_anthropic_key

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


class AgentUnavailable(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


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


def _sanitize_error(exc: Exception, api_key: str = "") -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text[:400]


async def _set_phase(emit: Emit, run_id: str, phase_id: int, status: str, detail: str = "") -> None:
    phase = next(p for p in PHASES if p["id"] == phase_id)
    await emit(
        "phase",
        {
            "runId": run_id,
            "phase": {**phase, "status": status, "detail": detail or phase["detail"]},
        },
    )


async def run_anthropic_loop(req: ChatRequest, emit: Emit, run_id: str, api_key: str) -> TradeRecommendation:
    try:
        import anthropic
    except ImportError as exc:
        raise AgentUnavailable("Anthropic SDK is not installed on the server") from exc

    runtime = await load_runtime_settings()
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
    last_error = ""

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
            last_error = _sanitize_error(exc, api_key)
            logger.warning("Anthropic call failed: %s", last_error)
            raise AgentUnavailable(f"Claude API error: {last_error}") from exc

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
                last_error = _sanitize_error(exc, api_key)
                logger.warning("Anthropic non-stream failed: %s", last_error)
                raise AgentUnavailable(f"Claude API error: {last_error}") from exc
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
            if text_acc.strip():
                await emit("assistant", {"runId": run_id, "text": text_acc.strip()})
                raise AgentUnavailable("Claude responded without a TradeRecommendation JSON")
            raise AgentUnavailable(last_error or "Claude returned an empty response")

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

    if rec:
        return rec
    raise AgentUnavailable("Claude tool loop ended without a TradeRecommendation")


async def run_claude_agent_sdk(req: ChatRequest, emit: Emit, run_id: str, api_key: str) -> TradeRecommendation | None:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    except Exception:
        return None

    server = try_build_sdk_server()
    if server is None:
        return None

    runtime = await load_runtime_settings()
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
        logger.warning("Claude Agent SDK failed, trying Messages API: %s", exc)
        await emit("thought", {"runId": run_id, "text": f"Agent SDK unavailable ({_sanitize_error(exc, api_key)}). Trying Messages API."})
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
    engine: str | None = None

    try:
        api_key = await resolve_anthropic_key()
        if not api_key:
            raise AgentUnavailable(
                "ANTHROPIC_API_KEY is missing. Save a real key in Settings — FoxAgent will not invent a setup."
            )

        rec = await run_claude_agent_sdk(req, emit, run_id, api_key)
        if rec:
            engine = "claude-agent-sdk"
        else:
            rec = await run_anthropic_loop(req, emit, run_id, api_key)
            engine = "anthropic-tools"
    except AgentUnavailable as exc:
        logger.warning("Agent unavailable: %s", exc.detail)
        await emit("error", {"runId": run_id, "detail": exc.detail})
        await emit("run_complete", {"runId": run_id, "engine": None, "recommendationId": None, "error": exc.detail})
        return {"runId": run_id, "engine": None, "recommendation": None, "error": exc.detail}

    await emit(
        "run_complete",
        {"runId": run_id, "engine": engine, "recommendationId": rec.id if rec else None},
    )
    return {"runId": run_id, "engine": engine, "recommendation": rec.model_dump(mode="json") if rec else None}
