from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.db import kv_set
from app.services.backtest.engine import conditions_ok
from app.services.briefing import build_briefing, format_briefing_html
from app.services.run_control import set_paused
from app.services.telegram_ops import handle_command, reset_telegram_ops, send_ops
from app.services.trading_bot.circuit import (
    is_halted,
    note_outcome,
    note_scan_error,
    reset_circuits_memory,
    set_safe_mode,
)
from app.services.trading_bot.coordinator import TradingBotCoordinator
from app.services.trading_bot.experiment import MAX_ATTEMPTS, reset_experiment_jobs, start_experiment
from app.services.trading_bot.news_candle_agent import NewsCandleAgent
from app.services.trading_bot.strategy_library import get_library, reset_library
from app.services.trading_bot.strategy_schema import BUILTIN_IDS, dsl_from_flags, flags_from_dsl


def _pass_report(**kwargs):
    data = dict(id="bt_pass", winRate=0.62, profitFactor=1.8, totalTrades=80, maxDrawdownR=6.0, totalR=22.0)
    data.update(kwargs)
    report = SimpleNamespace(**data)
    report.model_dump = lambda mode="json": dict(data)
    return report


def _fail_report():
    return _pass_report(id="bt_fail", winRate=0.40, profitFactor=0.9, totalTrades=12, maxDrawdownR=18.0, totalR=2.0)


def _draft(name: str) -> dict:
    return {
        "name": name,
        "description": "Fade after Asian sweep into FVG",
        "timeframes": ["M15"],
        "direction": "both",
        "entry_conditions": {"asian_sweep": True, "fvg_exists": True},
        "sessions": ["london", "london_ny_overlap"],
        "stop_rule": "beyond sweep wick",
        "tp1_r": 1.5,
        "tp2_r": 3.0,
        "max_holding_bars": 24,
    }


@pytest.fixture(autouse=True)
async def _clean(monkeypatch):
    import app.services.trading_bot.strategy_library as lab

    reset_library()
    reset_experiment_jobs()
    reset_circuits_memory()
    reset_telegram_ops()
    monkeypatch.setattr(lab, "SessionLocal", None)
    await kv_set("strategy_pins", json.dumps({sid: True for sid in BUILTIN_IDS}))
    await kv_set("strategy_circuits", "{}")
    await kv_set("desk_safe_mode", "0")
    await set_paused(False)
    yield
    await set_paused(False)
    reset_library()
    reset_experiment_jobs()
    reset_circuits_memory()
    reset_telegram_ops()


@pytest.mark.asyncio
async def test_validate_never_sets_active_even_with_auto_activate():
    lib = get_library()
    created = await lib.propose(_draft("Silent activate gold"))
    sid = created["strategy"]["id"]

    async def engine_run(**_kwargs):
        return _pass_report()

    result = await lib.validate(sid, engine_run=engine_run, auto_activate=True)
    assert result["ok"] and result["passed"]
    assert result["strategy"]["status"] == "validated"
    assert result["strategy"]["pinned"] is False
    assert sid not in {r.id for r in await lib.get_active_strategies()}


@pytest.mark.asyncio
async def test_unpin_builtin_leaves_library_but_exits_scan():
    lib = get_library()
    before = {r.id for r in await lib.get_active_strategies()}
    assert "gold_scalp" in before
    unpinned = await lib.pin("gold_scalp", False)
    assert unpinned["ok"]
    assert unpinned["strategy"]["pinned"] is False
    active = {r.id for r in await lib.get_active_strategies()}
    assert "gold_scalp" not in active
    kept = await lib.get("gold_scalp")
    assert kept is not None
    assert kept.source == "builtin"


@pytest.mark.asyncio
async def test_experiment_caps_at_eight_and_never_pins():
    calls = []

    async def engine_run(**_kwargs):
        calls.append(1)
        return _fail_report()

    result = await start_experiment(_draft("Eight-try gold"), engine_run=engine_run)
    assert result["ok"]
    job = result["job"]
    assert len(job["attempts"]) == MAX_ATTEMPTS == 8
    assert len(calls) == 8
    assert job["passed"] is False
    assert job["status"] == "exhausted"
    rule = await get_library().get(job["strategyId"])
    assert rule is not None
    assert rule.status != "active"
    assert rule.pinned is False


@pytest.mark.asyncio
async def test_experiment_pass_awaits_human_pin():
    async def engine_run(**_kwargs):
        return _pass_report()

    result = await start_experiment(_draft("Passable experiment"), engine_run=engine_run)
    assert result["job"]["status"] == "awaiting_pin"
    assert result["job"]["passed"] is True
    rule = await get_library().get(result["job"]["strategyId"])
    assert rule is not None
    assert rule.status == "validated"
    assert rule.pinned is False


def test_dsl_and_flags_same_engine_decision():
    flags = {"asian_sweep": True, "fvg_exists": True, "bos_confirmed": False}
    dsl = dsl_from_flags(flags, ["london"])
    report = SimpleNamespace(liquidity_sweep=True, fvgs=[{"id": 1}], last_bos=None)
    assert conditions_ok(flags, report) is True
    assert conditions_ok(dsl, report) is True
    assert flags_from_dsl(dsl)["asian_sweep"] is True
    empty = SimpleNamespace(liquidity_sweep=False, fvgs=[], last_bos=None)
    assert conditions_ok(flags, empty) is False
    assert conditions_ok(dsl, empty) is False


@pytest.mark.asyncio
async def test_circuit_halts_after_losses_and_pause_wins():
    for _ in range(4):
        row = await note_outcome("gold_scalp", False)
    assert row["halted"] is True
    assert await is_halted("gold_scalp")
    await set_paused(True)
    bot = TradingBotCoordinator()
    saved = await bot.run_cycle(SimpleNamespace(botAgents=["multi_strategy"], botActiveStrategies=[], botEnabled=True))
    assert saved == []


@pytest.mark.asyncio
async def test_safe_mode_after_scan_errors():
    for _ in range(5):
        await note_scan_error()
    assert await is_halted("gold_breakout")
    await set_safe_mode(False)
    reset_circuits_memory()


@pytest.mark.asyncio
async def test_telegram_rejects_foreign_chat(monkeypatch):
    async def creds():
        return "tok", ["111"], True

    monkeypatch.setattr("app.services.telegram_service._telegram_credentials", creds)
    denied = await handle_command("/status", "999")
    assert denied["ok"] is False
    assert "allow-listed" in denied["detail"]
    allowed = await handle_command("/pause", "111")
    assert allowed["ok"] is True
    assert allowed["paused"] is True
    await set_paused(False)


@pytest.mark.asyncio
async def test_telegram_skips_duplicate_ops(monkeypatch):
    sent = []

    async def fake_send(text, token="", chat_ids=None):
        sent.append(text)
        return {"ok": True}

    async def creds():
        return "tok", ["111"], True

    monkeypatch.setattr("app.services.telegram_ops.send_html", fake_send)
    monkeypatch.setattr("app.services.telegram_service._telegram_credentials", creds)
    first = await send_ops("news", "nfp-1", "High-impact in 20m: NFP")
    second = await send_ops("news", "nfp-1", "High-impact in 20m: NFP")
    assert first.get("ok") is True
    assert second.get("skipped") is True
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_briefing_empty_calendar(monkeypatch):
    async def empty_cal(**_kwargs):
        return {"events": [], "source": "", "warning": "scrape missed"}

    async def health():
        return {"timeframes": {"M15": {"stale": True}}}

    monkeypatch.setattr("app.services.economic_calendar.upcoming_events", empty_cal)
    monkeypatch.setattr("app.services.gold_warehouse.timeframe_health", health)
    body = await build_briefing()
    assert body["events24h"] == []
    html = format_briefing_html(body)
    assert "none from source" in html
    assert "M15" in html


@pytest.mark.asyncio
async def test_news_window_empty_without_events():
    async def no_events():
        return []

    status = await NewsCandleAgent(events_source=no_events).window_status()
    assert status["open"] is False
    assert status["windows"] == []
    assert status["sourceEvents"] == 0
