from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Awaitable

from app.schemas import ChatRequest, TradeRecommendation, new_id
from app.services.artifacts import ARTIFACT_PROTOCOL
from app.services.settings_store import resolve_anthropic_key

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

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
- A live chart PNG is attached on full-analysis turns. Read it. Call capture_chart_screenshot only if you need another timeframe or overlay. Use draw_on_chart to annotate structure you are reasoning about.
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
  "rationale": "3-5 short sentences in the trader's language (Arabic if they wrote Arabic) — no markdown headers, no emoji, no checklists",
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

Strategy Lab (XAU_USD only — never invent other pairs):
- list_strategies shows the single library the gold bot and backtest read from.
- propose_strategy saves a draft. Explain the idea, then wait for the operator before validate_strategy unless they explicitly ask to backtest it.
- validate_strategy runs the warehouse backtest (~2 years). Pause blocks validation. A strategy becomes live only after it clears the thresholds.
- Do not edit or delete builtin strategies.
""" + ARTIFACT_PROTOCOL


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


async def run_chat(req: ChatRequest, emit: Emit) -> dict[str, Any]:
    from app.services.crew import run_crew
    from app.services.session_store import append_session_event, ensure_session, save_session

    from app.services.token_usage import UsageTracker, bind_usage_tracker, reset_usage_tracker

    run_id = new_id("run")
    rec: TradeRecommendation | None = None
    final_text = ""
    session = await ensure_session(req.sessionId, req.symbol, req.timeframe)
    session_id = session["id"]
    tracker = UsageTracker(run_id=run_id, model=req.model or "")
    usage_token = bind_usage_tracker(tracker)
    await emit(
        "run_start",
        {
            "runId": run_id,
            "sessionId": session_id,
            "symbol": req.symbol,
            "model": req.model,
        },
    )
    await append_session_event(
        session_id,
        "message",
        {"role": "user", "text": req.message, "createdAt": __import__("time").time() * 1000},
    )

    async def complete(payload: dict[str, Any]) -> dict[str, Any]:
        usage = tracker.public()
        payload = {**payload, "usage": usage}
        await emit("usage", usage)
        await emit("run_complete", payload)
        return usage

    try:
        from app.services.run_control import RunCancelled, SystemPaused, clear_cancel, raise_if_paused

        await raise_if_paused()
        api_key = await resolve_anthropic_key()
        if not api_key:
            raise AgentUnavailable(
                "ANTHROPIC_API_KEY is missing. Save a real key in Settings — FoxAgent will not invent a setup."
            )
        rec, final_text = await run_crew(req, emit, run_id, api_key, session_id)
    except SystemPaused as exc:
        detail = str(exc)
        await emit("error", {"runId": run_id, "sessionId": session_id, "detail": detail, "paused": True})
        await complete({"runId": run_id, "sessionId": session_id, "engine": None, "paused": True, "error": detail})
        return {"runId": run_id, "sessionId": session_id, "engine": None, "recommendation": None, "error": detail, "paused": True}
    except RunCancelled:
        await emit("cancelled", {"runId": run_id, "sessionId": session_id})
        await complete({"runId": run_id, "sessionId": session_id, "engine": "multi-agent-crew", "cancelled": True})
        clear_cancel(run_id)
        return {"runId": run_id, "sessionId": session_id, "engine": "multi-agent-crew", "recommendation": None, "cancelled": True}
    except AgentUnavailable as exc:
        logger.warning("Agent unavailable: %s", exc.detail)
        await emit("error", {"runId": run_id, "sessionId": session_id, "detail": exc.detail})
        await complete(
            {
                "runId": run_id,
                "sessionId": session_id,
                "engine": None,
                "recommendationId": None,
                "error": exc.detail,
            }
        )
        return {
            "runId": run_id,
            "sessionId": session_id,
            "engine": None,
            "recommendation": None,
            "error": exc.detail,
        }
    finally:
        reset_usage_tracker(usage_token)

    if not session.get("title"):
        session["title"] = req.message.strip()[:80] or session.get("title") or req.symbol
    session["symbol"] = req.symbol
    session["timeframe"] = req.timeframe
    await save_session(session)

    if rec:
        await append_session_event(
            session_id,
            "message",
            {"role": "assistant", "text": rec.rationale, "recommendationId": rec.id, "usage": tracker.public()},
        )
    elif final_text.strip():
        await emit("assistant", {"runId": run_id, "text": final_text.strip()})
        await append_session_event(
            session_id,
            "message",
            {"role": "assistant", "text": final_text.strip(), "runId": run_id, "usage": tracker.public()},
        )

    usage = await complete(
        {
            "runId": run_id,
            "sessionId": session_id,
            "engine": "multi-agent-crew",
            "recommendationId": rec.id if rec else None,
        }
    )
    return {
        "runId": run_id,
        "sessionId": session_id,
        "engine": "multi-agent-crew",
        "recommendation": rec.model_dump(mode="json") if rec else None,
        "usage": usage,
    }
