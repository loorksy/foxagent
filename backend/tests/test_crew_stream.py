from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.schemas import ChatRequest, TradeAction, TradeRecommendation, TradeSetup, TakeProfitLevel, Sentiment
from app.services import agent as agent_mod
from app.services.crew import run_crew


def _rec() -> TradeRecommendation:
    return TradeRecommendation(
        symbol="XAU_USD",
        timeframe="15m",
        sentiment=Sentiment.BULLISH,
        tradeSetup=TradeSetup(
            action=TradeAction.BUY,
            entryPrice=2340.0,
            stopLoss=2330.0,
            takeProfitLevels=[
                TakeProfitLevel(level=1, price=2356.0, ratio="1:1.6"),
                TakeProfitLevel(level=2, price=2370.0, ratio="1:3.0"),
            ],
            riskRewardRatio=3.0,
        ),
        rationale="Approved after debate",
        confluence=["FVG", "session"],
    )


@pytest.mark.asyncio
async def test_crew_emits_real_event_contract(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    async def fake_turn(**kwargs):
        name = kwargs["name"]
        await kwargs["emit"]("agent_thought", {"agent": name, "delta": f"{name} weighs the FVG", "text": f"{name} weighs the FVG"})
        await kwargs["emit"](
            "agent_tool_call",
            {"agent": name, "name": "get_candles", "id": f"{name}-1", "input": {"instrument": "XAU_USD"}},
        )
        await kwargs["emit"](
            "agent_tool_result",
            {"agent": name, "name": "get_candles", "id": f"{name}-1", "output": {"count": 2}},
        )
        if name == "RiskManagerAgent":
            return json.dumps(_rec().model_dump(mode="json")), _rec()
        return f"{name} brief on liquidity", None

    async def fake_plain(**kwargs):
        return f"{kwargs['agent']} argument using the briefs"

    async def past_context(*_a, **_k):
        return "Warning: Previous setup on XAU/USD during NY open failed due to unmitigated lower-timeframe FVG"

    class Runtime:
        defaultClaudeModel = "claude-sonnet-4-5"

    async def load_runtime():
        return Runtime()

    async def fake_persist(rec, emit=None):
        dumped = rec.model_dump(mode="json")
        if emit:
            await emit("recommendation", dumped)
            await emit("agent_recommendation", dumped)
        return {"ok": True, "recommendation": dumped}

    monkeypatch.setattr("app.services.crew.run_agent_turn", fake_turn)
    monkeypatch.setattr("app.services.crew._stream_plain", fake_plain)
    monkeypatch.setattr("app.services.crew.get_past_context", past_context)
    monkeypatch.setattr("app.services.crew.load_runtime_settings", load_runtime)
    monkeypatch.setattr("app.services.crew.persist_recommendation", fake_persist)
    monkeypatch.setattr("app.services.crew.schedule_trade_alert", lambda rec: None)
    monkeypatch.setattr("app.services.memory_log.SessionLocal", None)
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)

    rec = await run_crew(
        ChatRequest(message="scan gold", symbol="XAU_USD", timeframe="15m"),
        emit,
        "run_test",
        "sk-ant-test",
        "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb",
    )
    kinds = [name for name, _ in events]
    assert rec is not None
    assert "agent_memory_recall" in kinds
    assert "agent_thought" in kinds
    assert "agent_tool_call" in kinds
    assert "agent_tool_result" in kinds
    assert "agent_debate_message" in kinds
    assert "agent_recommendation" in kinds
    assert not any(name.startswith("agent_artifact") for name in kinds)
    assert not any(name == "phase" for name in kinds)
    recall = next(p for n, p in events if n == "agent_memory_recall")
    assert "unmitigated" in recall["text"].lower()
    debates = [p for n, p in events if n == "agent_debate_message"]
    assert {d["role"] for d in debates} == {"bull", "bear"}


def test_algorithmic_and_phases_removed():
    assert not hasattr(agent_mod, "run_algorithmic")
    assert not hasattr(agent_mod, "PHASES")
    assert not hasattr(agent_mod, "run_anthropic_loop")


def test_sse_pipeline_forwards_crew_events(monkeypatch):
    async def fake_run(req, emit):
        await emit("agent_thought", {"agent": "TechnicalAgent", "delta": "mapping the 15m FVG"})
        await emit("agent_debate_message", {"role": "bull", "text": "take the long"})
        await emit("agent_artifact_start", {"id": "art_x", "title": "brief", "type": "ict_report"})
        return {"runId": "run_sse", "recommendation": None}

    monkeypatch.setattr("app.api.routes.run_chat", fake_run)
    from fastapi import FastAPI
    from app.api.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/agent/chat/stream",
        json={"message": "scan", "symbol": "XAU_USD", "timeframe": "15m"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert "agent_thought" in body
    assert "mapping the 15m FVG" in body
    assert "agent_debate_message" in body
    assert "agent_artifact_start" in body
