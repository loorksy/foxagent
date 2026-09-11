"""Three-agent trading crew (TradingAgents-inspired).

Pipeline extracted from TauricResearch/TradingAgents:
  AgentState sequential analysts → InvestDebateState (bull then bear) →
  risk judge → store_decision → later Reflector.update_with_outcome.

FoxAgent maps that onto TechnicalAgent, FundamentalAgent, a real two-turn
debate, and RiskManagerAgent. Thoughts, tools, debate, artifacts, and
memory recalls are streamed as they happen — never as canned phase labels.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.mcp_tools import persist_recommendation
from app.schemas import ChatRequest, TradeRecommendation, new_id
from app.services.agent import (
    SYSTEM_PROMPT,
    AgentUnavailable,
    _sanitize_error,
    extract_json_object,
    resolve_model,
)
from app.services.artifacts import ARTIFACT_PROTOCOL, ArtifactStreamParser, is_quick_question, strip_ant_artifacts
from app.services.mcp_tools import (
    dispatch_tool,
    mcp_tool_specs,
    reset_tool_emit,
    set_tool_emit,
    try_build_sdk_server,
    tool_capture_chart_screenshot,
)
from app.services.intent import (
    INTENT_ANALYSIS,
    INTENT_CHAT,
    INTENT_RECOMMENDATION,
    INTENT_STRATEGY,
    classify_intent,
    wants_macro,
)
from app.services.memory_log import get_past_context, store_decision
from app.services.sdk_runtime import (
    build_sdk_options,
    classify_sdk_failure,
    sdk_query_arg,
    stats as sdk_stats,
    vision_user_content,
)
from app.services.simulator import normalize_granularity
from app.services.risk_rules import RiskRejected
from app.services.run_control import DebateBudget, RunCancelled, raise_if_cancelled
from app.services.token_usage import record_model_usage
from app.services.session_store import append_session_event
from app.services.settings_store import load_runtime_settings
from app.services.telegram_service import schedule_trade_alert

DEBATE_MAX_ROUNDS = 2
DEBATE_MAX_SECONDS = 90.0

logger = logging.getLogger(__name__)

TOOL_NARRATION = (
    "\n\nTOOL NARRATION (mandatory, in the trader's language — Arabic if they wrote Arabic):\n"
    "Before every tool call, write ONE short present-tense phrase (max 8 words) describing what you "
    "are doing. Examples: أراجع شارت الربع ساعة / أقرأ الأخبار / أرسم خط الاتجاه / أراجع النماذج.\n"
    "After the tool returns, write ONE short past-tense confirmation: تمت معاينة الشارت / راجعت الأخبار.\n"
    "Never mention programmatic tool names (get_candles, draw_on_chart, capture_chart_screenshot, …).\n"
    "After draw_on_chart you will receive the annotated chart image — look at it and say whether the "
    "lines landed on the structure you intended; if not, draw again.\n"
)

TECHNICAL_SYSTEM = (
    SYSTEM_PROMPT
    + "\n\nYou are TechnicalAgent. Focus only on ICT / SMC: liquidity sweeps, "
    "order blocks, FVGs, displacement, multi-timeframe structure (1D → 4H → 15m). "
    "Use get_candles, calculate_ict_levels, structure_scan, capture_chart_screenshot, "
    "draw_on_chart, query_technical_memory, list_strategies, propose_strategy. "
    "For a full analysis you MUST visually inspect the attached chart image (or call "
    "capture_chart_screenshot if none is attached) before writing the brief. "
    "Use draw_on_chart to annotate FVGs, liquidity, or S/R you are reasoning about. "
    "Do not invent candle prints. Do not emit a final TradeRecommendation JSON — "
    "the RiskManagerAgent will decide. Keep the brief tight: under ~300 words, plain "
    "sections, no emoji, no giant markdown headers."
    + TOOL_NARRATION
)

FUNDAMENTAL_SYSTEM = (
    "You are FundamentalAgent for FoxAgent. English only. "
    "Focus on the UTC session clock, interest-rate / risk-on context, calendar risk, and news. "
    "Use get_economic_calendar (real USD prints that move gold — NFP, CPI, FOMC, GDP, claims), "
    "get_market_sentiment, fetch_financial_news, query_macro_memory. "
    "Do not invent economic prints. If events[] is empty or the feed failed, say so. "
    "Return a structured macro brief under ~250 words, no emoji, no giant markdown headers. "
    "Do not emit a TradeRecommendation JSON."
    + ARTIFACT_PROTOCOL
    + TOOL_NARRATION
)

BULL_SYSTEM = (
    "You are the bull researcher. Argue FOR taking a directional setup using ONLY "
    "the technical and fundamental briefs. Be concrete about POIs, session, and confluence. "
    "4–8 sentences. English only. Do not emit artifacts unless the trader asked for a standalone document."
    + ARTIFACT_PROTOCOL
)

BEAR_SYSTEM = (
    "You are the bear researcher. Argue AGAINST the proposed setup using ONLY "
    "the briefs and the bull argument. Attack unmitigated FVGs, session risk, "
    "calendar, and missing confluence. 4–8 sentences. English only. "
    "Do not emit artifacts unless the trader asked for a standalone document."
    + ARTIFACT_PROTOCOL
)

RISK_SYSTEM = (
    SYSTEM_PROMPT
    + "\n\nYou are RiskManagerAgent, the final arbiter. "
    "Use validate_risk_rules before approving. "
    "Honor recalled lessons — do not repeat documented failure modes. "
    "If you approve, call send_recommendation with a complete TradeRecommendation JSON "
    "AND emit the same JSON as your final assistant text. "
    "The \"rationale\" field MUST be written in the trader's language (Arabic if they wrote Arabic) "
    "and MUST be short: 3–5 plain sentences. No markdown headers, no emoji, no checklists, no "
    "position-sizing tables — the UI renders the levels in a card and the full internal briefs on a "
    "separate details screen, so never repeat them. "
    "If you reject, do not call send_recommendation and do not invent prices; reply in the trader's "
    "language with a short plain explanation (max 6 sentences): the decisive reason and what concrete "
    "condition would change your mind. "
    "You may call record_post_trade_reflection only when evaluating a closed trade."
    + TOOL_NARRATION
)

CHAT_SYSTEM = (
    "You are FoxAgent, a trading desk assistant specialized in gold (XAU/USD) and ICT / Smart Money "
    "analysis. You are ONE assistant backed by an internal desk team (technical analyst, macro analyst, "
    "risk manager) — never present the internal roles as separate personas; always speak as FoxAgent. "
    "Always reply in the language the user wrote in (Arabic in → Arabic out). "
    "Be concise and conversational: 1–6 short sentences, no markdown headers, no emoji walls, no "
    "checklists, no tables unless asked. "
    "You may call tools to answer factual market questions (price, candles, calendar, news). "
    "Never invent prices or news. Never output a TradeRecommendation JSON."
    + ARTIFACT_PROTOCOL
    + TOOL_NARRATION
)

ANALYSIS_SUMMARY_SYSTEM = (
    "You are FoxAgent's desk voice. You receive internal briefs from the technical and macro analysts. "
    "Write ONE concise reply to the trader in their language (Arabic in → Arabic out). "
    "Hard limits: at most 8 short sentences OR 6 short bullet points. No big markdown headers, no emoji "
    "spam, no trade recommendation JSON, and no entry/SL/TP levels unless the trader explicitly asked "
    "for levels. Lead with the direct answer, then the key evidence (structure, liquidity, session, "
    "calendar). If data was unavailable, say so plainly."
)

STRATEGY_SYSTEM = (
    "You are FoxAgent's strategy engineer for XAU_USD. "
    "Use list_strategies, propose_strategy, and validate_strategy to work on the strategy library. "
    "propose_strategy saves a draft; wait for the operator before validate_strategy unless they "
    "explicitly asked to backtest. Do not edit or delete builtin strategies. "
    "Reply in the user's language, concisely (max 8 short sentences). "
    "Never emit a TradeRecommendation JSON."
    + ARTIFACT_PROTOCOL
    + TOOL_NARRATION
)


def _looks_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in (text or ""))


def last_working_phrase(text: str) -> str:
    """Last short line the agent wrote — used as the live tool label."""
    if not text or not text.strip():
        return ""
    chunks: list[str] = []
    for line in text.replace("\r", "").split("\n"):
        line = line.strip().lstrip("-*#> ").strip()
        if line:
            chunks.append(line)
    if not chunks:
        return ""
    phrase = chunks[-1]
    if len(phrase) > 90:
        for sep in (". ", "。", "؟", "?", "!", "！"):
            if sep in phrase:
                phrase = phrase.rsplit(sep, 1)[-1].strip()
                break
        phrase = phrase[:90].rstrip()
    return phrase


def decorate_emit(emit: Any, session_id: str | None = None):
    """Attach agent-written labels to tool calls and persist images/overlays."""
    buf = {"text": ""}

    async def wrapped(event: str, payload: dict[str, Any]) -> None:
        p = dict(payload or {})
        if event == "agent_thought":
            delta = str(p.get("delta") or p.get("text") or "")
            buf["text"] = (buf["text"] + delta)[-4000:]
        elif event == "agent_tool_call" and not p.get("label"):
            phrase = last_working_phrase(buf["text"])
            if phrase:
                p["label"] = phrase
        await emit(event, p)
        if not session_id:
            return
        try:
            if event == "agent_image":
                await append_session_event(session_id, "image", p)
            elif event == "agent_chart_overlays":
                await append_session_event(session_id, "overlays", p)
        except Exception:
            logger.debug("session persist skipped for %s", event)

    return wrapped


async def _emit_persist(emit, session_id: str | None, kind: str, event: str, payload: dict[str, Any]) -> None:
    await emit(event, payload)
    if session_id:
        try:
            await append_session_event(session_id, kind, payload)
        except Exception:
            logger.debug("session persist skipped for %s", event)


async def _stream_plain(
    *,
    client: Any,
    model: str,
    system: str,
    user: str,
    emit: Any,
    agent: str,
    run_id: str,
    session_id: str | None,
    api_key: str,
    user_message: str = "",
    final_voice: bool = False,
) -> str:
    try:
        stream = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
            stream=True,
        )
    except Exception as exc:
        raise AgentUnavailable(f"Claude API error: {_sanitize_error(exc, api_key)}") from exc

    parts: list[str] = []
    last_usage: Any = None
    parser = ArtifactStreamParser(
        emit, session_id=session_id, agent=agent, run_id=run_id, user_message=user_message
    )
    async for event in stream:
        et = getattr(event, "type", "")
        if et in {"message_delta", "message_start"}:
            last_usage = event
            continue
        if et != "content_block_delta":
            continue
        delta = event.delta
        text = ""
        channel = "text"
        if getattr(delta, "type", "") == "thinking_delta":
            text = getattr(delta, "thinking", "") or ""
            channel = "thinking"
        elif getattr(delta, "type", "") == "text_delta":
            text = getattr(delta, "text", "") or ""
        if not text:
            continue
        parts.append(text)
        visible = text if channel == "thinking" else await parser.feed(text)
        if visible:
            await emit(
                "agent_thought",
                {
                    "runId": run_id,
                    "agent": agent,
                    "delta": visible,
                    "text": visible,
                    "channel": channel,
                    "final": final_voice and channel == "text",
                },
            )
    leftover = await parser.flush()
    raw = "".join(parts)
    await parser.ingest_complete(raw)
    if leftover:
        await emit(
            "agent_thought",
            {"runId": run_id, "agent": agent, "delta": leftover, "text": leftover, "final": final_voice},
        )
    await record_model_usage(last_usage, emit=emit, run_id=run_id, model=model, agent=agent, path="messages")
    return strip_ant_artifacts(raw) or raw.strip()


async def _try_sdk_turn(
    *,
    name: str,
    system: str,
    user: str,
    emit: Any,
    run_id: str,
    api_key: str,
    model: str,
    session_id: str | None = None,
    user_message: str = "",
    require_sdk: bool = False,
    image_b64: str | None = None,
    final_voice: bool = False,
) -> str | None:
    try:
        from claude_agent_sdk import ClaudeSDKClient
    except Exception as exc:
        reason = f"SDK import failed: {exc}"
        sdk_stats.record_config_error(reason)
        logger.error("SDK path config error for %s: %s", name, reason)
        raise AgentUnavailable(reason) from exc
    server = try_build_sdk_server()
    if server is None:
        reason = "SDK MCP server could not be built"
        sdk_stats.record_config_error(reason)
        logger.error("SDK path config error for %s: %s", name, reason)
        raise AgentUnavailable(reason)
    options = build_sdk_options(model=model, system=system, api_key=api_key, server=server)
    text_acc = ""
    parser = ArtifactStreamParser(
        emit, session_id=session_id, agent=name, run_id=run_id, user_message=user_message
    )
    emit_token = set_tool_emit(emit)
    try:
        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(sdk_query_arg(user, image_b64))
                async for msg in client.receive_response():
                    if type(msg).__name__ == "ResultMessage":
                        await record_model_usage(
                            msg, emit=emit, run_id=run_id, model=model, agent=name, path="sdk"
                        )
                        if getattr(msg, "is_error", False):
                            status = getattr(msg, "api_error_status", None)
                            detail = getattr(msg, "result", None) or getattr(msg, "errors", None)
                            raise RuntimeError(f"SDK ResultMessage error status={status} {detail}")
                        continue
                    content = getattr(msg, "content", None)
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        btype = getattr(block, "type", "") or type(block).__name__
                        if "Thinking" in str(btype) or btype == "thinking":
                            tok = getattr(block, "thinking", "") or ""
                            if tok:
                                await emit(
                                    "agent_thought",
                                    {"runId": run_id, "agent": name, "delta": tok, "text": tok},
                                )
                        elif hasattr(block, "text"):
                            text_acc += block.text
                            visible = await parser.feed(block.text)
                            if visible:
                                await emit(
                                    "agent_thought",
                                    {
                                        "runId": run_id,
                                        "agent": name,
                                        "delta": visible,
                                        "text": visible,
                                        "channel": "text",
                                        "final": final_voice,
                                    },
                                )
                        elif "ToolUse" in type(block).__name__ or btype == "tool_use":
                            await emit(
                                "agent_tool_call",
                                {
                                    "runId": run_id,
                                    "agent": name,
                                    "name": getattr(block, "name", ""),
                                    "id": getattr(block, "id", ""),
                                    "input": getattr(block, "input", {}) or {},
                                },
                            )
        except AgentUnavailable:
            raise
        except Exception as exc:
            kind = classify_sdk_failure(exc)
            reason = f"{type(exc).__name__}: {exc}"
            if kind == "config" or require_sdk:
                sdk_stats.record_config_error(reason)
                logger.error("SDK path failed for %s (config/required, no fallback): %s", name, reason)
                raise AgentUnavailable(f"SDK path failed: {reason}") from exc
            sdk_stats.record_fallback(reason)
            logger.error(
                "SDK path failed, reason: %s, falling back agent=%s runId=%s",
                reason,
                name,
                run_id,
            )
            return None
        leftover = await parser.flush()
        await parser.ingest_complete(text_acc)
        if leftover:
            await emit(
                "agent_thought",
                {"runId": run_id, "agent": name, "delta": leftover, "text": leftover, "channel": "text", "final": final_voice},
            )
        sdk_stats.record_success()
        return strip_ant_artifacts(text_acc) or text_acc
    finally:
        reset_tool_emit(emit_token)


async def run_agent_turn(
    *,
    name: str,
    system: str,
    user: str,
    emit: Any,
    run_id: str,
    api_key: str,
    model: str,
    session_id: str | None,
    tools: list[dict[str, Any]] | None = None,
    max_rounds: int = 8,
    user_message: str = "",
    image_b64: str | None = None,
    require_sdk: bool = False,
    final_voice: bool = False,
) -> tuple[str, TradeRecommendation | None]:
    sdk_text = await _try_sdk_turn(
        name=name,
        system=system,
        user=user,
        emit=emit,
        run_id=run_id,
        api_key=api_key,
        model=model,
        session_id=session_id,
        user_message=user_message,
        require_sdk=require_sdk,
        image_b64=image_b64,
        final_voice=final_voice,
    )
    if sdk_text is not None:
        parsed = extract_json_object(sdk_text)
        rec = None
        if parsed and "tradeSetup" in parsed:
            try:
                rec = TradeRecommendation.model_validate(parsed)
            except Exception:
                rec = None
        return sdk_text, rec

    try:
        import anthropic
    except ImportError as exc:
        raise AgentUnavailable("Anthropic SDK is not installed on the server") from exc

    client = anthropic.AsyncAnthropic(api_key=api_key)
    messages: list[dict[str, Any]] = [{"role": "user", "content": vision_user_content(user, image_b64)}]
    tool_specs = tools if tools is not None else mcp_tool_specs()
    final_text = ""
    text_acc = ""
    rec: TradeRecommendation | None = None
    use_thinking = True
    parser = ArtifactStreamParser(
        emit, session_id=session_id, agent=name, run_id=run_id, user_message=user_message
    )

    for _ in range(max_rounds):
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 12000 if use_thinking else 8000,
            "system": system,
            "tools": tool_specs,
            "messages": messages,
            "stream": True,
        }
        if use_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 6000}
        try:
            stream = await client.messages.create(**kwargs)
        except Exception as exc:
            err = _sanitize_error(exc, api_key)
            if use_thinking:
                logger.info("Thinking unsupported or rejected (%s); retrying without it", err)
                use_thinking = False
                continue
            raise AgentUnavailable(f"Claude API error: {err}") from exc

        text_acc = ""
        tool_uses: list[dict[str, Any]] = []
        last_usage: Any = None
        async for event in stream:
            et = getattr(event, "type", "")
            if et in {"message_delta", "message_start"}:
                last_usage = event
            if et == "content_block_start":
                block = getattr(event, "content_block", None)
                if block is not None and getattr(block, "type", None) == "tool_use":
                    tool_uses.append(
                        {"id": block.id, "name": block.name, "input": dict(getattr(block, "input", None) or {})}
                    )
                    await emit(
                        "agent_tool_call",
                        {
                            "runId": run_id,
                            "agent": name,
                            "name": block.name,
                            "id": block.id,
                            "input": dict(getattr(block, "input", None) or {}),
                        },
                    )
            elif et == "content_block_delta":
                delta = event.delta
                dt = getattr(delta, "type", "")
                if dt == "thinking_delta":
                    tok = getattr(delta, "thinking", "") or ""
                    if tok:
                        await emit("agent_thought", {"runId": run_id, "agent": name, "delta": tok, "text": tok})
                elif dt == "text_delta":
                    tok = getattr(delta, "text", "") or ""
                    if tok:
                        text_acc += tok
                        visible = await parser.feed(tok)
                        if visible:
                            await emit(
                                "agent_thought",
                                {"runId": run_id, "agent": name, "delta": visible, "text": visible, "channel": "text", "final": final_voice},
                            )

        if not text_acc and not tool_uses:
            try:
                msg = await client.messages.create(
                    model=model,
                    max_tokens=8000,
                    system=system,
                    tools=tool_specs,
                    messages=messages,
                )
            except Exception as exc:
                raise AgentUnavailable(f"Claude API error: {_sanitize_error(exc, api_key)}") from exc
            assistant_content = []
            for block in msg.content:
                if block.type == "text":
                    text_acc += block.text
                    visible = await parser.feed(block.text)
                    if visible:
                        await emit(
                            "agent_thought",
                            {
                                "runId": run_id,
                                "agent": name,
                                "delta": visible,
                                "text": visible,
                                "channel": "text",
                                "final": final_voice,
                            },
                        )
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append({"id": block.id, "name": block.name, "input": dict(block.input)})
                    assistant_content.append(
                        {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
                    )
                    await emit(
                        "agent_tool_call",
                        {
                            "runId": run_id,
                            "agent": name,
                            "name": block.name,
                            "id": block.id,
                            "input": dict(block.input),
                        },
                    )
            stop_reason = msg.stop_reason
            last_usage = msg
        else:
            stop_reason = "tool_use" if tool_uses else "end_turn"
            assistant_content = []
            if text_acc:
                assistant_content.append({"type": "text", "text": text_acc})
            assistant_content.extend(
                {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]} for t in tool_uses
            )
        await record_model_usage(
            last_usage, emit=emit, run_id=run_id, model=model, agent=name, path="messages"
        )

        parsed = extract_json_object(strip_ant_artifacts(text_acc) or text_acc)
        if parsed and "tradeSetup" in parsed:
            try:
                rec = TradeRecommendation.model_validate(parsed)
            except Exception:
                rec = None

        if stop_reason != "tool_use" or not tool_uses:
            final_text = text_acc
            break

        results = []
        for tu in tool_uses:
            try:
                out = await dispatch_tool(tu["name"], tu["input"], emit, tool_id=tu["id"], agent=name)
            except Exception as exc:
                out = {"error": str(exc)}
                await emit(
                    "agent_tool_result",
                    {
                        "runId": run_id,
                        "agent": name,
                        "name": tu["name"],
                        "id": tu["id"],
                        "output": out,
                    },
                )
            if session_id:
                await append_session_event(
                    session_id,
                    "tool",
                    {"agent": name, "name": tu["name"], "input": tu["input"], "output": out if not isinstance(out, str) else {"ok": True}},
                )
            if tu["name"] == "send_recommendation":
                payload = tu["input"].get("payload") or tu["input"]
                if isinstance(payload, dict) and "tradeSetup" in payload:
                    try:
                        rec = TradeRecommendation.model_validate(payload)
                    except Exception:
                        pass
            image_b64 = None
            if tu["name"] == "capture_chart_screenshot" and isinstance(out, str):
                image_b64 = out
            elif isinstance(out, dict) and out.get("image"):
                image_b64 = out.get("image") if isinstance(out.get("image"), str) and len(str(out.get("image"))) > 80 else None
            if image_b64:
                public = {k: v for k, v in (out.items() if isinstance(out, dict) else {"ok": True}.items()) if k != "image"}
                content = [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                    {"type": "text", "text": json.dumps(public or {"ok": True}, default=str)[:4000]},
                ]
            else:
                content = json.dumps(out, default=str)[:20_000]
            results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": content})

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": results})

    leftover = await parser.flush()
    raw = final_text or text_acc
    await parser.ingest_complete(raw)
    if leftover:
        await emit(
            "agent_thought",
            {"runId": run_id, "agent": name, "delta": leftover, "text": leftover, "channel": "text", "final": final_voice},
        )
    return strip_ant_artifacts(raw) or raw, rec


async def _run_debate(
    *,
    client: Any,
    model: str,
    debate_ctx: str,
    emit: Any,
    run_id: str,
    session_id: str,
    api_key: str,
    user_message: str,
) -> tuple[str, str]:
    """Bull and Bear each speak twice: opening, then rebuttal. Hard-capped."""
    budget = DebateBudget(max_rounds=DEBATE_MAX_ROUNDS, max_seconds=DEBATE_MAX_SECONDS)
    bull = ""
    bear = ""
    while budget.allow_another():
        raise_if_cancelled(run_id)
        round_no = budget.calls // 2 + 1
        if budget.calls % 2 == 0:
            prompt = debate_ctx if not bear else (
                f"{debate_ctx}\n\nBEAR ARGUMENT:\n{bear}\n\n"
                f"This is bull rebuttal round {round_no}. Answer the bear's specific points. "
                "Do not repeat your opening verbatim."
            )
            bull = await _stream_plain(
                client=client,
                model=model,
                system=BULL_SYSTEM,
                user=prompt,
                emit=emit,
                agent="BullResearcher",
                run_id=run_id,
                session_id=session_id,
                api_key=api_key,
                user_message=user_message,
            )
            await _emit_persist(
                emit,
                session_id,
                "debate",
                "agent_debate_message",
                {"runId": run_id, "role": "bull", "agent": "BullResearcher", "text": bull, "round": round_no},
            )
        else:
            prompt = (
                f"{debate_ctx}\n\nBULL ARGUMENT:\n{bull}\n\n"
                f"This is bear {'opening' if round_no == 1 else 'rebuttal'} round {round_no}. "
                "Attack the latest bull case."
            )
            bear = await _stream_plain(
                client=client,
                model=model,
                system=BEAR_SYSTEM,
                user=prompt,
                emit=emit,
                agent="BearResearcher",
                run_id=run_id,
                session_id=session_id,
                api_key=api_key,
                user_message=user_message,
            )
            await _emit_persist(
                emit,
                session_id,
                "debate",
                "agent_debate_message",
                {"runId": run_id, "role": "bear", "agent": "BearResearcher", "text": bear, "round": round_no},
            )
        budget.mark()
    return bull, bear


async def run_crew(
    req: ChatRequest,
    emit: Any,
    run_id: str,
    api_key: str,
    session_id: str,
) -> tuple[TradeRecommendation | None, str]:
    from app.services.run_control import raise_if_paused

    await raise_if_paused()
    raise_if_cancelled(run_id)
    try:
        return await _run_crew_body(req, emit, run_id, api_key, session_id)
    except RunCancelled:
        await emit("cancelled", {"runId": run_id, "sessionId": session_id})
        raise


async def _run_crew_body(
    req: ChatRequest,
    emit: Any,
    run_id: str,
    api_key: str,
    session_id: str,
) -> tuple[TradeRecommendation | None, str]:
    emit = decorate_emit(emit, session_id)
    runtime = await load_runtime_settings()
    model = resolve_model(req.model or runtime.defaultClaudeModel)

    try:
        import anthropic
    except ImportError as exc:
        raise AgentUnavailable("Anthropic SDK is not installed on the server") from exc
    client = anthropic.AsyncAnthropic(api_key=api_key)

    hist = ""
    try:
        from app.services.session_store import get_session

        session_state = await get_session(session_id)
        msgs = (session_state or {}).get("state", {}).get("messages") or []
        hist = "\n".join(f"{m.get('role', 'user')}: {m.get('text') or m.get('content') or ''}" for m in msgs[-8:])
    except Exception:
        hist = ""

    intent = await classify_intent(client, model, req.message, hist)
    await _emit_persist(
        emit, session_id, "intent", "agent_intent", {"runId": run_id, "intent": intent}
    )
    raise_if_cancelled(run_id)

    if intent == INTENT_CHAT:
        chat_user = f"{hist}\n\nUser message:\n{req.message}" if hist else req.message
        text, _ = await run_agent_turn(
            name="FoxAgent",
            system=CHAT_SYSTEM,
            user=chat_user,
            emit=emit,
            run_id=run_id,
            api_key=api_key,
            model=model,
            session_id=session_id,
            user_message=req.message,
            final_voice=True,
        )
        return None, text

    if intent == INTENT_STRATEGY:
        strat_user = (
            f"Instrument: {req.symbol}\nTimeframe: {req.timeframe}\n"
            f"{hist}\n\nTrader request:\n{req.message}"
        )
        text, _ = await run_agent_turn(
            name="StrategyAgent",
            system=STRATEGY_SYSTEM,
            user=strat_user,
            emit=emit,
            run_id=run_id,
            api_key=api_key,
            model=model,
            session_id=session_id,
            user_message=req.message,
            final_voice=True,
        )
        return None, text

    try:
        memory_block = await get_past_context(req.symbol, query=req.message)
    except Exception as exc:
        logger.warning("memory recall failed: %s", exc)
        memory_block = ""

    if memory_block:
        lessons = [chunk.strip() for chunk in memory_block.split("\n\n") if chunk.strip()]
        payload = {
            "runId": run_id,
            "instrument": req.symbol,
            "count": len(lessons),
            "text": memory_block,
            "lessons": lessons[:8],
        }
        await _emit_persist(emit, session_id, "recall", "agent_memory_recall", payload)

    memory_prefix = (
        f"Recalled lessons (do not repeat these failure modes):\n{memory_block}\n\n" if memory_block else ""
    )

    raise_if_cancelled(run_id)
    chart_b64: str | None = None
    if not is_quick_question(req.message):
        gran = normalize_granularity(req.timeframe)
        chart_b64 = await tool_capture_chart_screenshot(req.symbol, gran, 180)
        from app.services.mcp_tools import publish_chart_image

        await emit(
            "agent_tool_call",
            {
                "runId": run_id,
                "agent": "TechnicalAgent",
                "name": "capture_chart_screenshot",
                "id": "vision-forced",
                "input": {"instrument": req.symbol, "granularity": gran, "count": 180},
                "label": "معاينة الشارت" if _looks_arabic(req.message) else "Reading the chart",
            },
        )
        await emit(
            "agent_tool_result",
            {
                "runId": run_id,
                "agent": "TechnicalAgent",
                "name": "capture_chart_screenshot",
                "id": "vision-forced",
                "output": {"image": "png", "bytes": len(chart_b64)},
            },
        )
        await publish_chart_image(emit, chart_b64, title="chart")
        if session_id:
            await append_session_event(
                session_id,
                "tool",
                {
                    "agent": "TechnicalAgent",
                    "name": "capture_chart_screenshot",
                    "input": {"instrument": req.symbol, "granularity": gran},
                    "output": {"ok": True, "forced": True},
                },
            )
    tech_user = (
        f"Instrument: {req.symbol}\nTimeframe: {req.timeframe}\n"
        f"{memory_prefix}Trader request:\n{req.message}\n\n{hist}"
    )
    if chart_b64:
        tech_user += "\nA live chart PNG is attached. Read price structure from it before concluding."
    technical, _ = await run_agent_turn(
        name="TechnicalAgent",
        system=TECHNICAL_SYSTEM,
        user=tech_user,
        emit=emit,
        run_id=run_id,
        api_key=api_key,
        model=model,
        session_id=session_id,
        user_message=req.message,
        image_b64=chart_b64,
    )

    raise_if_cancelled(run_id)
    fundamental = ""
    if intent == INTENT_RECOMMENDATION or wants_macro(req.message):
        fund_user = (
            f"Instrument: {req.symbol}\nTimeframe: {req.timeframe}\n{memory_prefix}"
            f"Technical brief:\n{technical[:4000]}\n\nTrader request:\n{req.message}"
        )
        fundamental, _ = await run_agent_turn(
            name="FundamentalAgent",
            system=FUNDAMENTAL_SYSTEM,
            user=fund_user,
            emit=emit,
            run_id=run_id,
            api_key=api_key,
            model=model,
            session_id=session_id,
            user_message=req.message,
        )

    if intent == INTENT_ANALYSIS:
        raise_if_cancelled(run_id)
        summary_user = (
            f"Instrument: {req.symbol} {req.timeframe}\n\n"
            f"TECHNICAL BRIEF:\n{technical[:3500]}\n\n"
            + (f"MACRO BRIEF:\n{fundamental[:2500]}\n\n" if fundamental else "")
            + f"Trader question:\n{req.message}"
        )
        summary = await _stream_plain(
            client=client,
            model=model,
            system=ANALYSIS_SUMMARY_SYSTEM,
            user=summary_user,
            emit=emit,
            agent="FoxAgent",
            run_id=run_id,
            session_id=session_id,
            api_key=api_key,
            user_message=req.message,
            final_voice=True,
        )
        return None, summary or technical[:1200]

    debate_ctx = (
        f"Instrument {req.symbol} {req.timeframe}\n\n"
        f"TECHNICAL:\n{technical[:3500]}\n\nMACRO:\n{fundamental[:3500]}\n\n"
        f"TRADER:\n{req.message}"
    )
    raise_if_cancelled(run_id)
    bull, bear = await _run_debate(
        client=client,
        model=model,
        debate_ctx=debate_ctx,
        emit=emit,
        run_id=run_id,
        session_id=session_id,
        api_key=api_key,
        user_message=req.message,
    )

    raise_if_cancelled(run_id)
    risk_user = (
        f"Instrument: {req.symbol}\nTimeframe: {req.timeframe}\n{memory_prefix}"
        f"TECHNICAL BRIEF:\n{technical[:3000]}\n\nMACRO BRIEF:\n{fundamental[:3000]}\n\n"
        f"BULL:\n{bull}\n\nBEAR:\n{bear}\n\nTrader request:\n{req.message}\n\n"
        "Decide: approve a setup or reject. If you approve, send_recommendation + JSON."
    )
    risk_text, rec = await run_agent_turn(
        name="RiskManagerAgent",
        system=RISK_SYSTEM,
        user=risk_user,
        emit=emit,
        run_id=run_id,
        api_key=api_key,
        model=model,
        session_id=session_id,
        user_message=req.message,
    )

    if rec:
        rec.model = rec.model or model
        rec.analysis = {
            "technical": technical,
            "fundamental": fundamental,
            "bull": bull,
            "bear": bear,
            "risk": strip_ant_artifacts(risk_text) or risk_text,
        }
        try:
            await persist_recommendation(rec, emit)
        except RiskRejected as exc:
            await emit("error", {"runId": run_id, "detail": str(exc), "gate": exc.result})
            await append_session_event(
                session_id, "message", {"role": "assistant", "text": f"Risk gate rejected: {exc}", "runId": run_id}
            )
            raise AgentUnavailable(f"Risk gate rejected the setup: {exc}") from exc
        dumped = rec.model_dump(mode="json") | {"runId": run_id}
        await emit("agent_recommendation", dumped)
        await emit("recommendation", dumped)
        await append_session_event(session_id, "recommendation", dumped)
        action = rec.tradeSetup.action.value if hasattr(rec.tradeSetup.action, "value") else str(rec.tradeSetup.action)
        rating = rec.sentiment.value if hasattr(rec.sentiment, "value") else str(rec.sentiment)
        from app.services.memory_log import decision_summary

        await store_decision(
            entry_id=new_id("mem"),
            symbol=req.symbol,
            kind="risk",
            decision=decision_summary(recommendation_id=rec.id, symbol=req.symbol, action=action, rating=rating),
            rating=rating,
            recommendation_id=rec.id,
        )
        return rec, rec.rationale

    if risk_text.strip():
        return None, risk_text.strip()
    raise AgentUnavailable("RiskManagerAgent returned an empty response")
