from __future__ import annotations

import pytest

from app.services.memory_log import (
    cosine,
    embed_text,
    get_past_context,
    store_decision,
    update_with_outcome,
)
from app.services.reflection import deterministic_lesson, write_reflection


def test_embed_and_cosine_rank_similar_lessons():
    a = embed_text("XAU_USD NY open unmitigated FVG failed")
    b = embed_text("gold new york open FVG not mitigated")
    c = embed_text("EUR_USD london range fade")
    assert cosine(a, b) > cosine(a, c)


@pytest.mark.asyncio
async def test_store_recall_and_outcome(monkeypatch):
    monkeypatch.setattr("app.services.memory_log.SessionLocal", None)
    await store_decision(
        entry_id="mem_test_1",
        symbol="XAU_USD",
        kind="risk",
        decision="Long XAU at NY open into unmitigated 15m FVG",
        rating="BULLISH",
        recommendation_id="rec_test_1",
    )
    await update_with_outcome(
        recommendation_id="rec_test_1",
        outcome="STOPPED_OUT",
        pnl=-1.0,
        reflection="Warning: Previous setup on XAU/USD during NY open failed due to unmitigated lower-timeframe FVG",
    )
    ctx = await get_past_context("XAU_USD", query="NY open FVG gold")
    assert "XAU_USD" in ctx
    assert "REFLECTION" in ctx
    assert "unmitigated" in ctx.lower()


def test_deterministic_lesson_is_outcome_conditioned():
    win = deterministic_lesson("Bought the FVG", "HIT_TP2", 2.4)
    lose = deterministic_lesson("Bought the FVG", "STOPPED_OUT", -1.0)
    assert "HIT_TP2" in win and "+2.40" in win
    assert "STOPPED_OUT" in lose and "-1.00" in lose
    assert win != lose


@pytest.mark.asyncio
async def test_write_reflection_without_claude(monkeypatch):
    monkeypatch.setattr("app.services.memory_log.SessionLocal", None)

    async def no_key() -> str:
        return ""

    monkeypatch.setattr("app.services.reflection.resolve_anthropic_key", no_key)
    await store_decision(
        entry_id="mem_test_2",
        symbol="EUR_USD",
        kind="risk",
        decision="Fade London high without displacement",
        recommendation_id="rec_test_2",
    )
    result = await write_reflection("rec_test_2", "STOPPED_OUT", -0.8)
    assert result is not None
    assert result["status"] == "resolved"
    assert "STOPPED_OUT" in result["reflection"]
