"""Z.ai chat path. Calls the official overseas ZaiClient; it does not invent a local model."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.schemas import ChatRequest, TradeRecommendation
from app.services.agent import AgentUnavailable, Emit
from app.services.mcp_tools import compact_tool_output, dispatch_tool, mcp_tool_specs
from app.services.model_catalog import DEFAULT_ZAI_MODEL, resolve_model
from app.services.token_usage import record_model_usage

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 6
_TOOL_TEXT_LIMIT = 6000

_LABELS_EN = {
    "get_live_price": "Live price",
    "get_candles": "Candles",
    "capture_chart_screenshot": "Chart",
    "structure_scan": "Structure",
    "memory_recall": "Memory recall",
    "memory_capture": "Save memory",
    "send_recommendation": "Recommendation",
    "validate_risk_rules": "Risk check",
}
_LABELS_AR = {
    "get_live_price": "السعر الحي",
    "get_candles": "الشموع",
    "capture_chart_screenshot": "الشارت",
    "structure_scan": "الهيكل",
    "memory_recall": "استدعاء الذاكرة",
    "memory_capture": "حفظ في الذاكرة",
    "send_recommendation": "التوصية",
    "validate_risk_rules": "فحص المخاطر",
}


def _looks_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text or "")


def _label(name: str, user_message: str) -> str:
    table = _LABELS_AR if _looks_arabic(user_message) else _LABELS_EN
    return table.get(name, name)


def zai_tool_specs() -> list[dict[str, Any]]:
    tools = []
    for spec in mcp_tool_specs():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": spec["input_schema"],
                },
            }
        )
    return tools


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


def _message_dump(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        data = message.model_dump(exclude_none=True)
    elif isinstance(message, dict):
        data = dict(message)
    else:
        data = {"content": _content_text(getattr(message, "content", ""))}
    data["role"] = data.get("role") or "assistant"
    return data


def _tool_calls(message: Any) -> list[Any]:
    calls = getattr(message, "tool_calls", None)
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls")
    return list(calls or [])


def _call_name_args(call: Any) -> tuple[str, str, dict[str, Any]]:
    if isinstance(call, dict):
        call_id = str(call.get("id") or "")
        fn = call.get("function") or {}
        name = str(fn.get("name") or call.get("name") or "")
        raw = fn.get("arguments") if isinstance(fn, dict) else None
    else:
        call_id = str(getattr(call, "id", "") or "")
        fn = getattr(call, "function", None)
        name = str(getattr(fn, "name", "") or getattr(call, "name", "") or "")
        raw = getattr(fn, "arguments", None) if fn is not None else None
    if isinstance(raw, str):
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            args = {}
    elif isinstance(raw, dict):
        args = raw
    else:
        args = {}
    if not isinstance(args, dict):
        args = {}
    return call_id, name, args


def _create_sync(api_key: str, model: str, messages: list[dict[str, Any]]) -> Any:
    from zai import ZaiClient

    client = ZaiClient(api_key=api_key)
    return client.chat.completions.create(
        model=model,
        messages=messages,
        tools=zai_tool_specs(),
        tool_choice="auto",
        max_tokens=4096,
        temperature=0.3,
    )


def _sanitize(exc: Exception, api_key: str) -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text[:400]


def _tool_payload(name: str, out: Any) -> str:
    public = compact_tool_output(name, out)
    blob = json.dumps(public, default=str, ensure_ascii=False)
    if len(blob) > _TOOL_TEXT_LIMIT:
        return blob[:_TOOL_TEXT_LIMIT] + "…[truncated]"
    return blob


async def run_zai_chat(
    req: ChatRequest,
    emit: Emit,
    run_id: str,
    api_key: str,
    session_id: str,
) -> tuple[TradeRecommendation | None, str]:
    from app.services.long_term_memory import recall_for_prompt
    from app.services.memory_log import get_past_context
    from app.services.run_control import raise_if_cancelled, raise_if_paused
    from app.services.session_store import get_session

    await raise_if_paused()
    raise_if_cancelled(run_id)
    model = resolve_model(req.model or DEFAULT_ZAI_MODEL)

    try:
        import zai  # noqa: F401
    except ImportError as exc:
        raise AgentUnavailable("zai-sdk is not installed on the server") from exc

    hist = ""
    try:
        session_state = await get_session(session_id)
        msgs = (session_state or {}).get("state", {}).get("messages") or []
        hist = "\n".join(
            f"{m.get('role', 'user')}: {m.get('text') or m.get('content') or ''}" for m in msgs[-8:]
        )
    except Exception:
        hist = ""

    journal = ""
    layered = ""
    try:
        journal = await get_past_context(req.symbol, query=req.message)
        layered = await recall_for_prompt(req.symbol, req.message, session_id=session_id)
    except Exception as exc:
        logger.warning("memory recall failed: %s", exc)
    memory_block = "\n\n".join(part for part in (journal, layered) if part)
    if memory_block:
        lessons = [chunk.strip() for chunk in memory_block.split("\n\n") if chunk.strip()]
        await emit(
            "agent_memory_recall",
            {
                "runId": run_id,
                "instrument": req.symbol,
                "count": len(lessons),
                "text": memory_block,
                "lessons": lessons[:8],
            },
        )

    system = (
        "You are FoxAgent, a gold (XAU_USD) ICT desk assistant speaking as one voice. "
        "Reply in the operator's language. Use tools for prices, candles, news, and calendar — "
        "never invent prints, candles, or prices. Call memory_recall to open a stored memory by id, "
        "and memory_capture to store a durable preference, constraint, or scenario (not the whole chat). "
        "A trade setup is saved only by send_recommendation, which runs the risk gate. "
        "Pause is enforced by the server. Do not place broker orders yourself."
    )
    user = f"Instrument: {req.symbol}\nTimeframe: {req.timeframe}\n"
    if memory_block:
        user += f"\n{memory_block}\n"
    if hist:
        user += f"\nRecent session:\n{hist}\n"
    user += f"\nOperator:\n{req.message}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    recommendation: TradeRecommendation | None = None
    final_text = ""

    for _round in range(_MAX_ROUNDS):
        await raise_if_paused()
        raise_if_cancelled(run_id)
        try:
            response = await asyncio.to_thread(_create_sync, api_key, model, messages)
        except AgentUnavailable:
            raise
        except Exception as exc:
            raise AgentUnavailable(f"Z.ai request failed: {_sanitize(exc, api_key)}") from exc

        await record_model_usage(response, emit=emit, run_id=run_id, model=model, agent="FoxAgent", path="zai")
        choice = response.choices[0]
        message = choice.message
        reasoning = getattr(message, "reasoning_content", None) or ""
        if reasoning:
            await emit(
                "agent_thought",
                {
                    "runId": run_id,
                    "agent": "FoxAgent",
                    "delta": str(reasoning),
                    "text": str(reasoning),
                    "channel": "thought",
                },
            )
        calls = _tool_calls(message)
        messages.append(_message_dump(message))
        if not calls:
            final_text = _content_text(getattr(message, "content", "")).strip()
            if final_text:
                await emit(
                    "token",
                    {"runId": run_id, "agent": "FoxAgent", "delta": final_text, "text": final_text, "final": True},
                )
            return recommendation, final_text

        for index, call in enumerate(calls):
            call_id, name, args = _call_name_args(call)
            if not call_id:
                call_id = f"zai_{_round}_{index}"
            await emit(
                "agent_tool_call",
                {
                    "runId": run_id,
                    "agent": "FoxAgent",
                    "name": name,
                    "id": call_id,
                    "input": args,
                    "label": _label(name, req.message),
                },
            )
            try:
                out = await dispatch_tool(name, args, emit=emit, tool_id=call_id, agent="FoxAgent")
            except Exception as exc:
                out = {"ok": False, "error": _sanitize(exc, api_key)}
                await emit(
                    "agent_tool_result",
                    {
                        "runId": run_id,
                        "agent": "FoxAgent",
                        "name": name,
                        "id": call_id,
                        "output": out,
                    },
                )
            if name == "send_recommendation" and isinstance(out, dict) and isinstance(out.get("recommendation"), dict):
                try:
                    recommendation = TradeRecommendation.model_validate(out["recommendation"])
                except Exception:
                    recommendation = None
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _tool_payload(name, out),
                }
            )

    return recommendation, final_text
