from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.mcp_tools import dispatch_tool, mcp_tool_specs
from app.services.sdk_runtime import SDK_TOOLS
from app.services.trading_bot.multi_strategy_agent import MultiStrategyAgent
from app.services.trading_bot.strategy_library import get_library, reset_library, reset_library_store
from app.services.trading_bot.strategy_schema import BUILTIN_IDS, VALIDATION_THRESHOLDS, builtin_rules, evaluate_thresholds


def _pass_report(**kwargs):
    data = dict(
        id="bt_pass",
        winRate=0.62,
        profitFactor=1.8,
        totalTrades=80,
        maxDrawdownR=6.0,
        totalR=22.0,
    )
    data.update(kwargs)
    report = SimpleNamespace(**data)
    report.model_dump = lambda mode="json": dict(data)
    return report


def _fail_report():
    return _pass_report(id="bt_fail", winRate=0.40, profitFactor=0.9, totalTrades=12, maxDrawdownR=18.0, totalR=2.0)


def _draft_payload(name: str = "Asian FVG fade") -> dict:
    return {
        "name": name,
        "description": "Fade after Asian sweep into FVG",
        "timeframes": ["M15"],
        "direction": "both",
        "entry_conditions": {"asian_sweep": True, "fvg_exists": True},
        "stop_rule": "beyond sweep wick",
        "tp1_r": 1.5,
        "tp2_r": 3.0,
        "max_holding_bars": 24,
    }


@pytest.fixture(autouse=True)
async def _clean_lab():
    await reset_library_store()
    yield
    await reset_library_store()


def test_builtins_load():
    rules = builtin_rules()
    assert [r.id for r in rules] == list(BUILTIN_IDS)
    assert all(r.source == "builtin" and r.status == "active" for r in rules)
    assert VALIDATION_THRESHOLDS["min_win_rate"] == 0.55


@pytest.mark.asyncio
async def test_library_loads_builtins():
    lib = reset_library()
    rows = await lib.get_all()
    assert {r.id for r in rows} >= set(BUILTIN_IDS)
    active = await lib.get_active_strategies()
    assert {r.id for r in active} >= set(BUILTIN_IDS)


@pytest.mark.asyncio
async def test_claude_propose_and_list_mcp():
    proposed = await dispatch_tool("propose_strategy", _draft_payload("Claude gold fade"))
    assert proposed["ok"]
    assert proposed["strategy"]["source"] == "claude_proposed"
    assert proposed["strategy"]["status"] == "draft"
    listed = await dispatch_tool("list_strategies", {"status": "draft"})
    ids = {row["id"] for row in listed["strategies"]}
    assert proposed["strategy"]["id"] in ids


@pytest.mark.asyncio
async def test_manual_add():
    result = await get_library().propose(_draft_payload("Manual gold sweep"), source="manual", created_by="operator")
    assert result["ok"]
    assert result["strategy"]["source"] == "manual"
    assert result["strategy"]["status"] == "draft"


@pytest.mark.asyncio
async def test_validate_pass_then_approve():
    lib = get_library()
    created = await lib.propose(_draft_payload("Passable gold play"))
    sid = created["strategy"]["id"]

    async def engine_run(**_kwargs):
        return _pass_report()

    validated = await lib.validate(sid, engine_run=engine_run, auto_activate=False)
    assert validated["ok"] and validated["passed"]
    assert validated["strategy"]["status"] == "validated"
    approved = await lib.approve(sid)
    assert approved["ok"]
    assert approved["strategy"]["status"] == "active"
    active_ids = {r.id for r in await lib.get_active_strategies()}
    assert sid in active_ids


@pytest.mark.asyncio
async def test_validate_fail_rejects():
    lib = get_library()
    created = await lib.propose(_draft_payload("Weak gold play"))
    sid = created["strategy"]["id"]

    async def engine_run(**_kwargs):
        return _fail_report()

    result = await lib.validate(sid, engine_run=engine_run)
    assert result["ok"]
    assert result["passed"] is False
    assert result["strategy"]["status"] == "rejected"
    assert result["strategy"]["rejection_reason"]
    assert sid not in {r.id for r in await lib.get_active_strategies()}


@pytest.mark.asyncio
async def test_operator_reject_keeps_row():
    lib = get_library()
    created = await lib.propose(_draft_payload("Rejected gold idea"))
    sid = created["strategy"]["id"]
    rejected = await lib.reject(sid, "operator declined")
    assert rejected["ok"]
    kept = await lib.get(sid)
    assert kept is not None
    assert kept.status == "rejected"
    assert kept.rejection_reason == "operator declined"


@pytest.mark.asyncio
async def test_bot_reads_active_library_only():
    lib = get_library()
    created = await lib.propose(_draft_payload("Live library play"))
    sid = created["strategy"]["id"]

    async def engine_run(**_kwargs):
        return _pass_report()

    await lib.validate(sid, engine_run=engine_run, auto_activate=True)
    agent = MultiStrategyAgent(active=None)
    rules = await agent._rules()
    assert sid in {r.id for r in rules}
    await lib.archive(sid)
    hidden = await agent._rules()
    assert sid not in {r.id for r in hidden}
    assert set(BUILTIN_IDS) <= {r.id for r in hidden}


@pytest.mark.asyncio
async def test_duplicate_name_and_builtin_guard():
    lib = get_library()
    first = await lib.propose(_draft_payload("Unique gold name"))
    assert first["ok"]
    dup = await lib.propose(_draft_payload("Unique gold name"))
    assert dup["ok"] is False
    overwrite = await lib.propose({"name": "قناص سيولة الذهب", "id": "gold_liquidity_sniper"})
    assert overwrite["ok"] is False
    deleted = await lib.delete("gold_breakout")
    assert deleted["ok"] is False


@pytest.mark.asyncio
async def test_pause_blocks_validation():
    from app.services.run_control import set_paused

    lib = get_library()
    created = await lib.propose(_draft_payload("Paused gold play"))
    await set_paused(True)
    try:
        result = await lib.validate(created["strategy"]["id"], engine_run=lambda **_: _pass_report())
        assert result.get("paused") is True
        assert result["ok"] is False
    finally:
        await set_paused(False)


def test_mcp_and_sdk_register_strategy_tools():
    names = {spec["name"] for spec in mcp_tool_specs()}
    for tool in ("propose_strategy", "validate_strategy", "list_strategies"):
        assert tool in names
        assert f"mcp__oanda__{tool}" in SDK_TOOLS


def test_thresholds_helper():
    passed, reasons = evaluate_thresholds(_pass_report())
    assert passed and not reasons
    failed, why = evaluate_thresholds(_fail_report())
    assert not failed and why


def test_rest_strategy_api(client, auth_header):
    listed = client.get("/api/strategies", headers=auth_header)
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()["strategies"]}
    assert set(BUILTIN_IDS) <= ids

    created = client.post("/api/strategies", headers=auth_header, json=_draft_payload("API gold draft"))
    assert created.status_code == 200
    sid = created.json()["strategy"]["id"]

    proposed = client.get("/api/strategies/proposed", headers=auth_header)
    assert proposed.status_code == 200
    assert any(row["id"] == sid for row in proposed.json()["strategies"])

    patched = client.patch(f"/api/strategies/{sid}", headers=auth_header, json={"description": "updated"})
    assert patched.status_code == 200
    assert patched.json()["strategy"]["description"] == "updated"

    detail = client.get(f"/api/strategies/{sid}", headers=auth_header)
    assert detail.status_code == 200
    assert detail.json()["id"] == sid

    rejected = client.post(f"/api/strategies/{sid}/reject", headers=auth_header, json={"reason": "not now"})
    assert rejected.status_code == 200
    assert rejected.json()["strategy"]["status"] == "rejected"

    gone = client.delete(f"/api/strategies/{sid}", headers=auth_header)
    assert gone.status_code == 400

    builtin = client.delete("/api/strategies/gold_scalp", headers=auth_header)
    assert builtin.status_code == 400


def test_rest_validate_approve_with_fake_engine(client, auth_header, monkeypatch):
    class FakeEngine:
        async def run(self, **_kwargs):
            return _pass_report()

    monkeypatch.setattr("app.services.backtest.engine.BacktestEngine", FakeEngine)
    created = client.post("/api/strategies", headers=auth_header, json=_draft_payload("API validated play"))
    sid = created.json()["strategy"]["id"]
    validated = client.post(f"/api/strategies/{sid}/validate", headers=auth_header, json={"days": 730})
    assert validated.status_code == 200
    body = validated.json()
    assert body["passed"] is True
    assert body["strategy"]["status"] == "validated"
    approved = client.post(f"/api/strategies/{sid}/approve", headers=auth_header)
    assert approved.status_code == 200
    assert approved.json()["strategy"]["status"] == "active"


@pytest.mark.asyncio
async def test_rest_validate_paused(client, auth_header):
    from app.services.run_control import set_paused

    created = client.post("/api/strategies", headers=auth_header, json=_draft_payload("Paused API play"))
    sid = created.json()["strategy"]["id"]
    await set_paused(True)
    try:
        resp = client.post(f"/api/strategies/{sid}/validate", headers=auth_header, json={})
        assert resp.status_code == 409
    finally:
        await set_paused(False)
