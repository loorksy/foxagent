from __future__ import annotations

import pytest

from app.db import _memory_recs, _memory_settings
from app.services.inbox import ack_item, approve_signal, list_items, reject_signal, snapshot
from app.services.run_control import reset_for_tests
from app.services.trading_bot.store import reset_bot_memory, reset_bot_store, save_signal, signal_payload


async def _fresh_health(*_a, **_k):
    return {
        "symbol": "XAU_USD",
        "timeframes": {"M15": {"stale": False}, "H1": {"stale": False}, "H4": {"stale": False}, "D": {"stale": False}},
    }


async def _stale_health(*_a, **_k):
    return {
        "symbol": "XAU_USD",
        "timeframes": {"M15": {"stale": True}, "H1": {"stale": False}, "H4": {"stale": False}, "D": {"stale": False}},
    }


async def _wipe_recs() -> None:
    from app.db import RecommendationRow, SessionLocal
    from sqlalchemy import delete

    _memory_recs.clear()
    _memory_settings.pop("inbox_acks", None)
    if SessionLocal is None:
        return
    async with SessionLocal() as session:
        await session.execute(delete(RecommendationRow))
        await session.commit()
    from app.db import kv_set

    await kv_set("inbox_acks", "[]")


@pytest.fixture(autouse=True)
async def _clean(monkeypatch):
    reset_for_tests()
    await reset_bot_store()
    reset_bot_memory()
    await _wipe_recs()
    monkeypatch.setattr("app.services.gold_warehouse.timeframe_health", _fresh_health)
    monkeypatch.setattr(
        "app.services.risk_rules.current_session",
        lambda: {"session": "london", "label": "London"},
    )

    async def no_news(*_a, **_k):
        return {"events": []}

    monkeypatch.setattr("app.services.economic_calendar.upcoming_events", no_news)
    yield
    await reset_bot_store()
    reset_bot_memory()
    await _wipe_recs()
    reset_for_tests()


def _sig(**kwargs):
    body = dict(
        agent_type="multi_strategy",
        strategy_id="gold_liquidity_sniper",
        timeframe="M15",
        signal_type="buy",
        entry=100.0,
        stop=99.5,
        tp1=101.5,
        tp2=103.0,
        confidence=0.91,
        risk_reward=3.0,
    )
    body.update(kwargs)
    return signal_payload(**body)


@pytest.mark.asyncio
async def test_empty_inbox():
    items = await list_items()
    assert items == []
    snap = await snapshot()
    assert snap["counts"]["open"] == 0


@pytest.mark.asyncio
async def test_pending_signal_is_approval_card():
    await save_signal(_sig(signal_id="sig_inbox_1"))
    items = await list_items()
    assert len(items) == 1
    assert items[0]["tab"] == "approvals"
    assert items[0]["id"] == "signal:sig_inbox_1"
    assert items[0]["kind"] == "signal"


@pytest.mark.asyncio
async def test_reject_keeps_row_with_reason():
    await save_signal(_sig(signal_id="sig_rej"))
    result = await reject_signal("signal:sig_rej", "overlap already filled")
    assert result["ok"] is True
    from app.services.trading_bot.store import get_signal

    row = await get_signal("sig_rej")
    assert row["status"] == "rejected"
    assert row["metadata"]["rejectionReason"] == "overlap already filled"
    open_items = await list_items()
    assert open_items == []


@pytest.mark.asyncio
async def test_reject_requires_reason():
    await save_signal(_sig(signal_id="sig_noreason"))
    result = await reject_signal("signal:sig_noreason", "  ")
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_approve_goes_through_risk_gate(monkeypatch):
    gated = {"n": 0}
    real = __import__("app.services.mcp_tools", fromlist=["persist_recommendation"]).persist_recommendation

    async def wrap(payload, emit=None):
        gated["n"] += 1
        return await real(payload, emit)

    monkeypatch.setattr("app.services.trading_bot.promote.persist_recommendation", wrap)
    await save_signal(_sig(signal_id="sig_ok"))
    result = await approve_signal("signal:sig_ok")
    assert result.get("ok") is True
    assert gated["n"] == 1
    assert result.get("recommendation")
    from app.services.trading_bot.store import get_signal

    row = await get_signal("sig_ok")
    assert row["status"] == "active"
    assert row["recommendationId"]


@pytest.mark.asyncio
async def test_approve_cannot_skip_risk_gate(monkeypatch):
    await save_signal(
        _sig(signal_id="sig_bad", risk_reward=0.4, stop=90.0, tp2=100.4)
    )
    result = await approve_signal("sig_bad")
    assert result.get("ok") is not True
    from app.services.trading_bot.store import get_signal

    row = await get_signal("sig_bad")
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_ack_hides_alert_not_approval(monkeypatch):
    monkeypatch.setattr("app.services.gold_warehouse.timeframe_health", _stale_health)
    alerts = await list_items()
    assert any(i["id"] == "warehouse:stale" for i in alerts)
    acked = await ack_item("warehouse:stale")
    assert acked["ok"] is True
    assert all(i["id"] != "warehouse:stale" for i in await list_items())

    await save_signal(_sig(signal_id="sig_ack"))
    blocked = await ack_item("signal:sig_ack")
    assert blocked["ok"] is False
    assert any(i["id"] == "signal:sig_ack" for i in await list_items())


def test_inbox_http_empty(client, auth_header):
    resp = client.get("/api/inbox", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("items"), list)
    assert "open" in (body.get("counts") or {})
    assert "paused" in (body.get("desk") or {})
