from __future__ import annotations

import pytest

from app.db import _memory_recs, list_recommendations
from app.schemas import ChatRequest, Sentiment, TakeProfitLevel, TradeAction, TradeRecommendation, TradeSetup
from app.services.agent import AgentUnavailable
from app.services.crew import run_crew
from app.services.mcp_tools import persist_recommendation
from app.services.risk_rules import RiskRejected


def _runtime(min_rr=2.0, max_risk=1.0, sessions=None):
    class Runtime:
        minRiskReward = min_rr
        maxRiskPercent = max_risk
        allowedSessions = sessions or ["london", "ny", "asian"]

    return Runtime()


def _payload(*, entry=100.0, sl=99.5, tp=103.0, rr=3.0, risk_percent=None) -> dict:
    setup = {
        "action": "BUY",
        "orderType": "LIMIT",
        "entryPrice": entry,
        "stopLoss": sl,
        "takeProfitLevels": [{"level": 1, "price": tp, "ratio": "1:3"}],
        "riskRewardRatio": rr,
    }
    if risk_percent is not None:
        setup["riskPercent"] = risk_percent
    return {
        "symbol": "XAU_USD",
        "timeframe": "15m",
        "sentiment": "BULLISH",
        "tradeSetup": setup,
        "rationale": "gate test",
        "confluence": [],
    }


@pytest.fixture
def memory_db(monkeypatch):
    monkeypatch.setattr("app.services.memory_log.SessionLocal", None)
    monkeypatch.setattr("app.db.SessionLocal", None)
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)
    _memory_recs.clear()
    yield
    _memory_recs.clear()


@pytest.fixture
def risk_runtime(monkeypatch):
    async def load():
        return _runtime()

    monkeypatch.setattr("app.services.risk_rules.load_runtime_settings", load)
    monkeypatch.setattr("app.services.telegram_service.schedule_trade_alert", lambda rec: None)
    monkeypatch.setattr(
        "app.services.risk_rules.current_session",
        lambda now=None: {"session": "london", "utcHour": 8},
    )


@pytest.mark.asyncio
async def test_persist_rejects_low_rr_and_writes_nothing(memory_db, risk_runtime):
    with pytest.raises(RiskRejected) as exc:
        await persist_recommendation(_payload(rr=0.5, tp=100.2))
    assert any("R:R" in r for r in exc.value.result["reasons"])
    assert await list_recommendations() == []


@pytest.mark.asyncio
async def test_persist_rejects_disallowed_session_and_writes_nothing(memory_db, monkeypatch):
    async def load():
        return _runtime(sessions=["ny"])

    monkeypatch.setattr("app.services.risk_rules.load_runtime_settings", load)
    monkeypatch.setattr("app.services.telegram_service.schedule_trade_alert", lambda rec: None)
    monkeypatch.setattr(
        "app.services.risk_rules.current_session",
        lambda now=None: {"session": "asian", "utcHour": 3},
    )
    with pytest.raises(RiskRejected) as exc:
        await persist_recommendation(_payload())
    assert any("Session" in r for r in exc.value.result["reasons"])
    assert await list_recommendations() == []


@pytest.mark.asyncio
async def test_persist_rejects_risk_percent_over_max_and_writes_nothing(memory_db, risk_runtime):
    # |100-90|/100 = 10% > maxRiskPercent 1.0
    with pytest.raises(RiskRejected) as exc:
        await persist_recommendation(_payload(entry=100.0, sl=90.0, tp=130.0, rr=3.0))
    assert any("Implied risk" in r for r in exc.value.result["reasons"])
    assert await list_recommendations() == []


@pytest.mark.asyncio
async def test_persist_accepts_payload_that_passes_all_three_checks(memory_db, risk_runtime):
    result = await persist_recommendation(_payload())
    assert result["ok"] is True
    rows = await list_recommendations()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "XAU_USD"


@pytest.mark.asyncio
async def test_crew_cannot_bypass_gate_by_skipping_validate_tool(memory_db, risk_runtime, monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    failing = TradeRecommendation(
        id="rec_bypass",
        symbol="XAU_USD",
        timeframe="15m",
        sentiment=Sentiment.BULLISH,
        tradeSetup=TradeSetup(
            action=TradeAction.BUY,
            entryPrice=100.0,
            stopLoss=90.0,
            takeProfitLevels=[TakeProfitLevel(level=1, price=130.0, ratio="1:3")],
            riskRewardRatio=3.0,
        ),
        rationale="model never called validate_risk_rules",
    )

    async def fake_turn(**kwargs):
        if kwargs["name"] == "RiskManagerAgent":
            return failing.model_dump_json(), failing
        return f"{kwargs['name']} brief", None

    async def fake_plain(**kwargs):
        return f"{kwargs['agent']} argument"

    class Runtime:
        defaultClaudeModel = "claude-sonnet-4-5"

    async def past_context(*_a, **_k):
        return ""

    async def load_runtime():
        return Runtime()

    monkeypatch.setattr("app.services.crew.run_agent_turn", fake_turn)
    monkeypatch.setattr("app.services.crew._stream_plain", fake_plain)
    monkeypatch.setattr("app.services.crew.get_past_context", past_context)
    monkeypatch.setattr("app.services.crew.load_runtime_settings", load_runtime)
    monkeypatch.setattr("app.services.settings_store.load_runtime_settings", load_runtime)
    monkeypatch.setattr("app.services.crew.schedule_trade_alert", lambda rec: None)

    with pytest.raises(AgentUnavailable):
        await run_crew(
            ChatRequest(message="setup", symbol="XAU_USD", timeframe="15m"),
            emit,
            "run_gate",
            "sk-ant-test",
            "dddddddd-4444-4444-8444-dddddddddddd",
        )
    assert await list_recommendations() == []
    assert not any(n == "agent_recommendation" for n, _ in events)
