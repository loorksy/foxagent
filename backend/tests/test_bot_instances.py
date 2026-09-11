from __future__ import annotations

import pytest

from app.services.trading_bot.coordinator import TradingBotCoordinator, reset_coordinator
from app.services.trading_bot.instances import (
    DEFAULT_BOT_ID,
    DEFAULT_BOT_NAME,
    BotInstance,
    ensure_default_instance,
    execute_signal_order,
    get_instance,
    list_instances,
    reset_instances_store,
    reset_manager,
    save_instance,
)
from app.services.trading_bot.multi_strategy_agent import MultiStrategyAgent
from app.services.trading_bot.store import (
    get_signal,
    reset_bot_memory,
    reset_bot_store,
    save_signal,
    signal_payload,
)


@pytest.fixture(autouse=True)
async def _clean():
    from app.services.run_control import reset_for_tests, set_paused

    reset_for_tests()
    reset_coordinator()
    reset_manager()
    await reset_instances_store()
    await reset_bot_store()
    yield
    from app.services.trading_bot.instances import get_manager

    await get_manager().stop_all()
    # Clear instances BEFORE unpausing so resume has nothing to restart.
    await reset_instances_store()
    await set_paused(False)
    reset_for_tests()
    reset_manager()
    await reset_bot_store()
    reset_bot_memory()
    reset_coordinator()


class _GateRuntime:
    minRiskReward = 2.0
    maxRiskPercent = 1.0
    allowedSessions = ["london", "ny", "asian", "london_ny_overlap", "late_ny_asia", "asia", "london_close"]


def _risk_ok(monkeypatch):
    async def load():
        return _GateRuntime()

    session = {"session": "london", "utcHour": 10}
    monkeypatch.setattr("app.services.risk_rules.load_runtime_settings", load)
    monkeypatch.setattr("app.services.risk_rules.current_session", lambda now=None: session)
    monkeypatch.setattr("app.services.macro_feed.current_session", lambda now=None: session)
    monkeypatch.setattr("app.services.trading_bot.coordinator.current_session", lambda now=None: session)


def _valid_signal(**overrides):
    payload = signal_payload(
        agent_type="multi_strategy",
        strategy_id="gold_trend_follow",
        timeframe="H1",
        signal_type="buy",
        entry=2650,
        stop=2647,
        tp1=2654.5,
        tp2=2659,
        confidence=0.9,
        risk_reward=3.0,
    )
    payload.update(overrides)
    return payload


def _mt5(monkeypatch, connected: bool):
    async def is_connected():
        return connected

    monkeypatch.setattr("app.services.metaapi.is_connected", is_connected)


# ---------------------------------------------------------------------- CRUD


async def test_instance_crud_api(client, auth_header):
    listed = client.get("/api/bots/instances", headers=auth_header)
    assert listed.status_code == 200
    names = [i["name"] for i in listed.json()["instances"]]
    assert DEFAULT_BOT_NAME in names  # migration created the default gold bot

    created = client.post(
        "/api/bots/instances",
        headers=auth_header,
        json={
            "name": "بوت اختبار",
            "type": "strategy",
            "scanIntervalSeconds": 30,
            "agents": ["multi_strategy"],
            "strategyIds": ["gold_scalp"],
            "minRr": 2.5,
            "maxRiskPercent": 0.5,
        },
    )
    assert created.status_code == 200
    bot = created.json()
    assert bot["type"] == "strategy"
    assert bot["strategyIds"] == ["gold_scalp"]
    assert bot["minRr"] == 2.5

    listed = client.get("/api/bots/instances", headers=auth_header)
    assert any(i["id"] == bot["id"] for i in listed.json()["instances"])

    patched = client.patch(
        f"/api/bots/instances/{bot['id']}",
        headers=auth_header,
        json={"name": "بوت معدل", "minRr": 3.0},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "بوت معدل"
    assert patched.json()["minRr"] == 3.0

    signals = client.get(f"/api/bots/instances/{bot['id']}/signals", headers=auth_header)
    assert signals.status_code == 200
    assert signals.json()["signals"] == []

    deleted = client.delete(f"/api/bots/instances/{bot['id']}", headers=auth_header)
    assert deleted.status_code == 200
    listed = client.get("/api/bots/instances", headers=auth_header)
    assert not any(i["id"] == bot["id"] for i in listed.json()["instances"])

    missing = client.get("/api/bots/instances/no-such-bot/signals", headers=auth_header)
    assert missing.status_code == 404


async def test_create_requires_name_and_known_type(client, auth_header):
    resp = client.post("/api/bots/instances", headers=auth_header, json={"type": "strategy"})
    assert resp.status_code == 400
    resp = client.post("/api/bots/instances", headers=auth_header, json={"name": "x", "type": "hedge_fund"})
    assert resp.status_code == 400


# ----------------------------------------------------------------- execution


async def test_execution_creation_blocked_without_mt5(client, auth_header, monkeypatch):
    _mt5(monkeypatch, False)
    resp = client.post(
        "/api/bots/instances",
        headers=auth_header,
        json={"name": "بوت تنفيذ", "type": "execution"},
    )
    assert resp.status_code == 400
    assert "MT5" in resp.json()["detail"]

    _mt5(monkeypatch, True)
    resp = client.post(
        "/api/bots/instances",
        headers=auth_header,
        json={"name": "بوت تنفيذ", "type": "execution", "orderVolume": 0.02},
    )
    assert resp.status_code == 200
    bot = resp.json()
    assert bot["type"] == "execution"
    assert bot["orderVolume"] == 0.02

    # Enabling later is also gated on a live MT5 link.
    _mt5(monkeypatch, False)
    resp = client.patch(f"/api/bots/instances/{bot['id']}", headers=auth_header, json={"enabled": True})
    assert resp.status_code == 400
    resp = client.post(f"/api/bots/instances/{bot['id']}/start", headers=auth_header)
    assert resp.status_code == 400


async def test_auto_execute_places_order_after_risk_gates(monkeypatch):
    inst = BotInstance(name="تنفيذ", type="execution", enabled=True, autoExecute=True, orderVolume=0.05)
    await save_instance(inst)
    _risk_ok(monkeypatch)
    _mt5(monkeypatch, True)
    orders: list[dict] = []

    async def place(symbol, side, volume, stop_loss=None, take_profit=None, comment=""):
        orders.append({"symbol": symbol, "side": side, "volume": volume, "sl": stop_loss, "tp": take_profit})
        return {"orderId": "ord-1"}

    monkeypatch.setattr("app.services.metaapi.place_market_order", place)
    coord = TradingBotCoordinator()
    coord.instance = inst
    stored = await coord._accept(_valid_signal(), _GateRuntime())
    assert stored is not None
    assert len(orders) == 1
    assert orders[0]["symbol"] == "XAUUSD"
    assert orders[0]["side"] == "BUY"
    assert orders[0]["volume"] == 0.05
    row = await get_signal(stored["id"])
    assert row["status"] == "executed"
    assert (row["metadata"].get("order") or {}).get("orderId") == "ord-1"
    assert row["botId"] == inst.id


async def test_auto_execute_never_bypasses_pause(monkeypatch):
    from app.services.run_control import set_paused

    inst = BotInstance(name="تنفيذ", type="execution", enabled=True, autoExecute=True)
    await save_instance(inst)
    _mt5(monkeypatch, True)
    orders: list[dict] = []

    async def place(*args, **kwargs):
        orders.append({})
        return {"orderId": "x"}

    monkeypatch.setattr("app.services.metaapi.place_market_order", place)
    payload = _valid_signal(botId=inst.id)
    await save_signal(payload)
    await set_paused(True)
    result = await execute_signal_order(payload["id"], trigger="auto")
    assert result is None
    assert orders == []
    await set_paused(False)


async def test_approval_executes_order_for_execution_bot(monkeypatch):
    inst = BotInstance(name="تنفيذ", type="execution", enabled=True, autoExecute=False, orderVolume=0.03)
    await save_instance(inst)
    _risk_ok(monkeypatch)
    _mt5(monkeypatch, True)
    orders: list[dict] = []

    async def place(symbol, side, volume, stop_loss=None, take_profit=None, comment=""):
        orders.append({"symbol": symbol, "side": side, "volume": volume})
        return {"orderId": "ord-appr"}

    monkeypatch.setattr("app.services.metaapi.place_market_order", place)
    payload = _valid_signal(botId=inst.id)
    await save_signal(payload)

    from app.services.inbox import approve_signal

    result = await approve_signal(f"signal:{payload['id']}")
    assert result["ok"] is True
    assert result.get("order", {}).get("orderId") == "ord-appr"
    assert len(orders) == 1
    assert orders[0]["volume"] == 0.03
    row = await get_signal(payload["id"])
    assert (row["metadata"].get("order") or {}).get("orderId") == "ord-appr"


# -------------------------------------------------------------------- alerts


async def test_alerts_signals_skip_approval_queue(monkeypatch):
    inst = BotInstance(name="تنبيهات", type="alerts", enabled=True)
    await save_instance(inst)
    _risk_ok(monkeypatch)
    pings: list[dict] = []
    monkeypatch.setattr("app.services.telegram_service.schedule_bot_signal", lambda s: pings.append(s))

    coord = TradingBotCoordinator()
    coord.instance = inst
    stored = await coord._accept(_valid_signal(), _GateRuntime())
    assert stored is not None
    assert stored["mode"] == "alert"
    assert stored["metadata"]["botId"] == inst.id
    assert pings, "alerts still notify via telegram"

    from app.services.inbox import _signal_items, approve_signal

    items = await _signal_items()
    assert all((i.get("payload") or {}).get("signal", {}).get("id") != stored["id"] for i in items)

    refused = await approve_signal(f"signal:{stored['id']}")
    assert refused["ok"] is False


# ---------------------------------------------------------------- per-instance


async def test_per_instance_cycle_uses_instance_strategy_ids(monkeypatch):
    inst = BotInstance(
        name="كمي",
        type="quant",
        enabled=True,
        agents=["multi_strategy"],
        strategyIds=["gold_trend_follow"],
    )
    await save_instance(inst)

    async def source(_i, _g, _n):
        return []

    coord = TradingBotCoordinator()
    coord.instance = inst
    coord.multi_strategy_agent = MultiStrategyAgent(candle_source=source)

    class Runtime:
        botAgents = ["multi_strategy", "pattern_notes", "news_candle"]
        botActiveStrategies = ["gold_scalp"]
        botMinRr = 2.0
        botMaxRiskPercent = 1.0
        botAllowedSessions: list[str] = []

    saved = await coord.run_cycle(Runtime())
    assert isinstance(saved, list)
    assert coord.multi_strategy_agent.active == ["gold_trend_follow"]


# --------------------------------------------------------------------- pause


async def test_pause_freezes_all_instances():
    from app.services.run_control import set_paused
    from app.services.trading_bot.instances import get_manager

    manager = get_manager()
    a = BotInstance(name="أ", type="strategy", enabled=True, scanIntervalSeconds=3600)
    b = BotInstance(name="ب", type="alerts", enabled=True, scanIntervalSeconds=3600)
    await save_instance(a)
    await save_instance(b)
    await manager.start_instance(a.id)
    await manager.start_instance(b.id)
    snaps = {s["id"]: s for s in await manager.list_snapshots()}
    assert snaps[a.id]["running"] is True
    assert snaps[b.id]["running"] is True

    await set_paused(True)
    snaps = {s["id"]: s for s in await manager.list_snapshots()}
    assert snaps[a.id]["running"] is False
    assert snaps[b.id]["running"] is False

    # Pause supremacy: starting while paused keeps the loop frozen.
    started = await manager.start_instance(a.id)
    assert started["paused"] is True
    assert started["running"] is False

    await set_paused(False)
    snaps = {s["id"]: s for s in await manager.list_snapshots()}
    assert snaps[a.id]["running"] is True
    assert snaps[b.id]["running"] is True
    await manager.stop_all()


# ----------------------------------------------------------------- migration


async def test_default_instance_migration():
    inst = await ensure_default_instance()
    assert inst is not None
    assert inst.id == DEFAULT_BOT_ID
    assert inst.name == DEFAULT_BOT_NAME
    assert inst.type == "strategy"
    assert set(inst.agents) <= {"multi_strategy", "pattern_notes", "news_candle"}

    # Idempotent: a second boot does not duplicate the default bot.
    again = await ensure_default_instance()
    assert again is not None and again.id == DEFAULT_BOT_ID
    assert len(await list_instances()) == 1

    # Deleting it and re-booting must NOT resurrect it (seed marker).
    from app.services.trading_bot.instances import delete_instance

    await delete_instance(DEFAULT_BOT_ID)
    assert await ensure_default_instance() is None
    assert await get_instance(DEFAULT_BOT_ID) is None
