from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.analysis import calculate_ict_levels
from app.services.macro_feed import current_session
from app.services.mcp_tools import dispatch_tool, mcp_tool_specs
from app.services.risk_rules import validate_risk_rules
from app.services.simulator import generate_candles


def test_session_clock_is_real_utc():
    asian = current_session(datetime(2026, 1, 1, 3, tzinfo=timezone.utc))
    london = current_session(datetime(2026, 1, 1, 8, tzinfo=timezone.utc))
    ny = current_session(datetime(2026, 1, 1, 17, tzinfo=timezone.utc))
    assert asian["session"] == "asian"
    assert london["session"] == "london"
    assert ny["session"] == "ny"


@pytest.mark.asyncio
async def test_validate_risk_rules_enforces_rr(monkeypatch):
    class Runtime:
        minRiskReward = 2.0
        maxRiskPercent = 1.0
        allowedSessions = ["london", "ny", "asian"]

    async def load():
        return Runtime()

    monkeypatch.setattr("app.services.risk_rules.load_runtime_settings", load)
    ok = await validate_risk_rules(
        {"entryPrice": 100, "stopLoss": 99, "takeProfitLevels": [{"price": 103}], "riskRewardRatio": 3}
    )
    bad = await validate_risk_rules(
        {"entryPrice": 100, "stopLoss": 99, "takeProfitLevels": [{"price": 100.5}], "riskRewardRatio": 0.5}
    )
    assert ok["ok"] is True
    assert bad["ok"] is False
    assert "R:R" in bad["reasons"][0]


def test_calculate_ict_levels_returns_structure():
    candles = generate_candles("XAU_USD", "M15", 120)
    levels = calculate_ict_levels(candles)
    assert "bias" in levels
    assert "fvgs" in levels
    assert "orderBlockZones" in levels


def test_required_agent_tools_are_registered():
    names = {spec["name"] for spec in mcp_tool_specs()}
    for required in (
        "get_candles",
        "capture_chart_screenshot",
        "calculate_ict_levels",
        "query_technical_memory",
        "get_economic_calendar",
        "get_market_sentiment",
        "fetch_financial_news",
        "query_macro_memory",
        "validate_risk_rules",
        "send_recommendation",
        "record_post_trade_reflection",
        "draw_on_chart",
    ):
        assert required in names


@pytest.mark.asyncio
async def test_dispatch_calendar_is_honest():
    data = await dispatch_tool("get_economic_calendar", {"instrument": "XAU_USD"})
    assert data["source"] == "session-clock"
    assert "note" in data
    assert "windows" in data
