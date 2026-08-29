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
from app.services.artifacts import ARTIFACT_PROTOCOL, ArtifactStreamParser, strip_ant_artifacts
from app.services.mcp_tools import dispatch_tool, mcp_tool_specs, try_build_sdk_server
from app.services.memory_log import get_past_context, store_decision
from app.services.risk_rules import RiskRejected
from app.services.run_control import DebateBudget, RunCancelled, raise_if_cancelled
from app.services.session_store import append_session_event
from app.services.settings_store import load_runtime_settings
from app.services.telegram_service import schedule_trade_alert

DEBATE_MAX_ROUNDS = 2
DEBATE_MAX_SECONDS = 90.0

logger = logging.getLogger(__name__)

TECHNICAL_SYSTEM = (
    SYSTEM_PROMPT
    + "\n\nYou are TechnicalAgent. Focus only on ICT / SMC: liquidity sweeps, "
    "order blocks, FVGs, displacement, multi-timeframe structure (1D → 4H → 15m). "
    "Use get_candles, calculate_ict_levels, structure_scan, capture_chart_screenshot, "
    "query_technical_memory. Return a structured technical brief. "
    "Do not invent candle prints. Do not emit a final TradeRecommendation JSON — "
    "the RiskManagerAgent will decide."
)

FUNDAMENTAL_SYSTEM = (
    "You are FundamentalAgent for FoxAgent. English only. "
    "Focus on the UTC session clock, interest-rate / risk-on context, calendar risk, and news. "
    "Use get_economic_calendar, get_market_sentiment, fetch_financial_news, query_macro_memory. "
    "Do not invent economic prints. If a feed is empty or failed, say so. "
    "Return a structured macro brief. Do not emit a TradeRecommendation JSON."
    + ARTIFACT_PROTOCOL
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
    "If you reject, do not call send_recommendation and do not invent prices. "
    "You may call record_post_trade_reflection only when evaluating a closed trade."
)


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
    parser = ArtifactStreamParser(
        emit, session_id=session_id, agent=agent, run_id=run_id, user_message=user_message
    )
    async for event in stream:
        if getattr(event, "type", "") != "content_block_delta":
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
                {"runId": run_id, "agent": agent, "delta": visible, "text": visible, "channel": channel},
            )
    leftover = await parser.flush()
    raw = "".join(parts)
    await parser.ingest_complete(raw)
    if leftover:
        await emit("agent_thought", {"runId": run_id, "agent": agent, "delta": leftover, "text": leftover})
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
) -> str | None:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    except Exception:
        return None
    server = try_build_sdk_server()
    if server is None:
        return None
    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system,
        mcp_servers={"oanda": server},
        allowed_tools=[
            "mcp__oanda__get_candles",
            "mcp__oanda__get_live_price",
            "mcp__oanda__capture_chart_screenshot",
            "mcp__oanda__structure_scan",
            "mcp__oanda__calculate_ict_levels",
            "mcp__oanda__query_technical_memory",
            "mcp__oanda__get_economic_calendar",
            "mcp__oanda__get_market_sentiment",
            "mcp__oanda__fetch_financial_news",
            "mcp__oanda__query_macro_memory",
            "mcp__oanda__validate_risk_rules",
            "mcp__oanda__send_recommendation",
            "mcp__oanda__record_post_trade_reflection",
        ],
        permission_mode="acceptEdits",
        env={"ANTHROPIC_API_KEY": api_key},
        max_turns=8,
    )
    text_acc = ""
    parser = ArtifactStreamParser(
        emit, session_id=session_id, agent=name, run_id=run_id, user_message=user_message
    )
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user)
            async for msg in client.receive_response():
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
    except Exception as exc:
        logger.warning("SDK turn failed for %s: %s", name, exc)
        return None
    leftover = await parser.flush()
    await parser.ingest_complete(text_acc)
    if leftover:
        await emit("agent_thought", {"runId": run_id, "agent": name, "delta": leftover, "text": leftover, "channel": "text"})
    return strip_ant_artifacts(text_acc) or text_acc


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
    )
    if sdk_text:
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
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
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
        async for event in stream:
            et = getattr(event, "type", "")
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
                                {"runId": run_id, "agent": name, "delta": visible, "text": visible, "channel": "text"},
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
        else:
            stop_reason = "tool_use" if tool_uses else "end_turn"
            assistant_content = []
            if text_acc:
                assistant_content.append({"type": "text", "text": text_acc})
            assistant_content.extend(
                {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]} for t in tool_uses
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
                out = await dispatch_tool(tu["name"], tu["input"], emit)
            except Exception as exc:
                out = {"error": str(exc)}
            await emit(
                "agent_tool_result",
                {
                    "runId": run_id,
                    "agent": name,
                    "name": tu["name"],
                    "id": tu["id"],
                    "output": out if not isinstance(out, str) else {"image": "png"},
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
            if tu["name"] == "capture_chart_screenshot" and isinstance(out, str):
                content: Any = [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": out}}
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
        await emit("agent_thought", {"runId": run_id, "agent": name, "delta": leftover, "text": leftover, "channel": "text"})
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
) -> TradeRecommendation | None:
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
) -> TradeRecommendation | None:
    runtime = await load_runtime_settings()
    model = resolve_model(req.model or runtime.defaultClaudeModel)

    try:
        import anthropic
    except ImportError as exc:
        raise AgentUnavailable("Anthropic SDK is not installed on the server") from exc
    client = anthropic.AsyncAnthropic(api_key=api_key)

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

    hist = ""
    session_state = None
    try:
        from app.services.session_store import get_session

        session_state = await get_session(session_id)
        msgs = (session_state or {}).get("state", {}).get("messages") or []
        hist = "\n".join(f"{m.get('role', 'user')}: {m.get('text') or m.get('content') or ''}" for m in msgs[-8:])
    except Exception:
        hist = ""

    memory_prefix = (
        f"Recalled lessons (do not repeat these failure modes):\n{memory_block}\n\n" if memory_block else ""
    )

    raise_if_cancelled(run_id)
    tech_user = (
        f"Instrument: {req.symbol}\nTimeframe: {req.timeframe}\n"
        f"{memory_prefix}Trader request:\n{req.message}\n\n{hist}"
    )
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
    )

    raise_if_cancelled(run_id)
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
        await store_decision(
            entry_id=new_id("mem"),
            symbol=req.symbol,
            kind="risk",
            decision=json.dumps(dumped, default=str)[:4000],
            rating=rec.sentiment.value if hasattr(rec.sentiment, "value") else str(rec.sentiment),
            recommendation_id=rec.id,
        )
        return rec

    if risk_text.strip():
        await emit("assistant", {"runId": run_id, "text": risk_text.strip()})
        await append_session_event(
            session_id, "message", {"role": "assistant", "text": risk_text.strip(), "runId": run_id}
        )
        raise AgentUnavailable("RiskManagerAgent rejected the setup or returned no TradeRecommendation JSON")
    raise AgentUnavailable("RiskManagerAgent returned an empty response")
