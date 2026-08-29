from __future__ import annotations

import pytest

from app.schemas import ChatRequest
from app.services.crew import DEBATE_MAX_ROUNDS, _run_debate, run_crew
from app.services.run_control import DebateBudget


@pytest.mark.asyncio
async def test_debate_makes_four_calls_in_order_and_stops(monkeypatch):
    calls: list[str] = []

    async def fake_plain(**kwargs):
        calls.append(kwargs["agent"])
        return f"{kwargs['agent']} line {len(calls)}"

    persisted: list[dict] = []

    async def fake_persist(emit, session_id, kind, event, payload):
        persisted.append(payload)
        await emit(event, payload)

    monkeypatch.setattr("app.services.crew._stream_plain", fake_plain)
    monkeypatch.setattr("app.services.crew._emit_persist", fake_persist)

    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    class Client:
        pass

    bull, bear = await _run_debate(
        client=Client(),
        model="claude-sonnet-4-5",
        debate_ctx="ctx",
        emit=emit,
        run_id="run_debate",
        session_id="eeeeeeee-5555-4555-8555-eeeeeeeeeeee",
        api_key="sk-test",
        user_message="scan",
    )
    assert calls == ["BullResearcher", "BearResearcher", "BullResearcher", "BearResearcher"]
    assert len(calls) == DEBATE_MAX_ROUNDS * 2
    assert [p["role"] for p in persisted] == ["bull", "bear", "bull", "bear"]
    assert bull.startswith("BullResearcher")
    assert bear.startswith("BearResearcher")


def test_debate_budget_hard_caps_rounds():
    budget = DebateBudget(max_rounds=2, max_seconds=60)
    allowed = 0
    while budget.allow_another():
        budget.mark()
        allowed += 1
        if allowed > 10:
            break
    assert allowed == 4


@pytest.mark.asyncio
async def test_crew_debate_transcript_has_four_tagged_entries(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    async def fake_turn(**kwargs):
        return f"{kwargs['name']} brief", None

    async def fake_plain(**kwargs):
        return f"{kwargs['agent']} argument {kwargs['user'][:12]}"

    async def fake_persist(rec, emit=None):
        return {"ok": True, "recommendation": None}

    class Runtime:
        defaultClaudeModel = "claude-sonnet-4-5"

    async def load_runtime():
        return Runtime()

    async def past(*_a, **_k):
        return ""

    monkeypatch.setattr("app.services.crew.run_agent_turn", fake_turn)
    monkeypatch.setattr("app.services.crew._stream_plain", fake_plain)
    monkeypatch.setattr("app.services.crew.get_past_context", past)
    monkeypatch.setattr("app.services.crew.load_runtime_settings", load_runtime)
    monkeypatch.setattr("app.services.crew.persist_recommendation", fake_persist)
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)

    with pytest.raises(Exception):
        await run_crew(
            ChatRequest(message="scan gold", symbol="XAU_USD", timeframe="15m"),
            emit,
            "run_debate_crew",
            "sk-ant-test",
            "ffffffff-6666-4666-8666-ffffffffffff",
        )
    debates = [p for n, p in events if n == "agent_debate_message"]
    assert len(debates) == 4
    assert [d["role"] for d in debates] == ["bull", "bear", "bull", "bear"]
    assert all(d.get("round") in {1, 2} for d in debates)
