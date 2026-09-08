from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import OHLCV
from app.services.backtest.engine import (
    BacktestEngine,
    apply_slippage,
    max_drawdown_r,
    profit_factor,
    simulate_trade,
    _group_month,
    _group_session,
)
from app.services.backtest.models import BacktestTrade
from app.services.backtest.rules import SLIPPAGE, SPREAD_COST, STRATEGY_RULES
from app.services.backtest.store import get_report, reset_backtest_memory
from app.services.gold_warehouse import delete_by_source, reset_memory, upsert_candles


def _c(i: int, o: float, h: float, l: float, c: float, start: datetime | None = None) -> OHLCV:
    base = start or datetime(2025, 1, 6, tzinfo=timezone.utc)  # Monday
    t = base + timedelta(minutes=15 * i)
    return OHLCV(time=t, timestamp=int(t.timestamp() * 1000), open=o, high=h, low=l, close=c, volume=100, complete=True)


def _trade(**kwargs) -> BacktestTrade:
    now = datetime(2025, 3, 3, 10, tzinfo=timezone.utc)
    payload = dict(
        strategyId="gold_breakout",
        timeframe="M15",
        entryTime=now,
        exitTime=now + timedelta(hours=1),
        direction="buy",
        entryPrice=2000,
        stopLoss=1999,
        takeProfit1=2001.5,
        takeProfit2=2003,
        exitPrice=2001.5,
        pnlR=1.0,
        pnlPercent=1.0,
        exitReason="tp1",
    )
    payload.update(kwargs)
    return BacktestTrade.model_validate(payload)


def _ranging(n: int = 220, start_px: float = 2640.0) -> list[OHLCV]:
    out = []
    px = start_px
    for i in range(n):
        drift = 0.15 if i % 5 else -0.1
        o = px
        c = px + drift
        out.append(_c(i, o, max(o, c) + 0.4, min(o, c) - 0.4, c))
        px = c
    return out


def _seed_series() -> list[OHLCV]:
    candles = _ranging(240)
    # Impulse close to encourage scalp / structure bias on the last signal bar.
    last_i = 200
    o = candles[last_i].close
    candles[last_i] = _c(last_i, o, o + 8, o - 0.3, o + 7.4)
    return candles


@pytest.fixture
async def seeded_warehouse():
    reset_memory()
    candles = _seed_series()
    yield candles
    reset_memory()
    reset_backtest_memory()


@pytest.mark.asyncio
async def test_backtest_runs_on_seeded_data(seeded_warehouse):
    await upsert_candles("M15", seeded_warehouse, source="backtest-fixture")
    try:
        report = await BacktestEngine().run(timeframe="M15", days=30, candles=seeded_warehouse, min_rr=1.0)
        assert report.candlesTested > 0
        assert report.totalTrades >= 0
        assert report.symbol == "XAU_USD"
    finally:
        await delete_by_source("M15", "backtest-fixture")


@pytest.mark.asyncio
async def test_no_lookahead_bias(seeded_warehouse, monkeypatch):
    seen: list[int] = []
    from app.services import analysis as analysis_mod
    from app.services.backtest import engine as engine_mod

    original = analysis_mod.analyze_structure

    def wrapped(candles):
        seen.append(candles[-1].timestamp)
        return original(candles)

    monkeypatch.setattr(engine_mod, "analyze_structure", wrapped)
    candles = seeded_warehouse
    await BacktestEngine().run(timeframe="M15", days=30, candles=candles, min_rr=1.0)
    assert seen
    assert max(seen) <= candles[-2].timestamp


def test_stop_loss_before_tp1():
    bars = [_c(0, 100, 102, 98, 99)]
    sim = simulate_trade(
        side="buy",
        entry=100,
        stop=99,
        tp1=101.5,
        tp2=103,
        tp1_r=1.5,
        tp2_r=3.0,
        bars=bars,
        max_holding_bars=4,
        apply_spread=False,
    )
    assert sim["exitReason"] == "stop_loss"
    assert sim["pnlR"] == -1.0


def test_tp1_partial_exit():
    bars = [_c(0, 100.1, 101.6, 100.05, 101.2), _c(1, 101.2, 101.3, 100.4, 100.6)]
    sim = simulate_trade(
        side="buy",
        entry=100,
        stop=99,
        tp1=101.5,
        tp2=103,
        tp1_r=1.5,
        tp2_r=3.0,
        bars=bars,
        max_holding_bars=6,
        apply_spread=False,
    )
    assert sim["exitReason"] in {"tp1", "timeout"}
    assert 0.6 <= sim["pnlR"] <= 1.6


def test_tp2_full_profit():
    bars = [_c(0, 100.1, 101.6, 100.1, 101.4), _c(1, 101.4, 103.2, 101.2, 103.0)]
    sim = simulate_trade(
        side="buy",
        entry=100,
        stop=99,
        tp1=101.5,
        tp2=103,
        tp1_r=1.5,
        tp2_r=3.0,
        bars=bars,
        max_holding_bars=6,
        apply_spread=False,
    )
    assert sim["exitReason"] == "tp2"
    assert sim["pnlR"] == pytest.approx(2.25, abs=0.01)


def test_breakeven_after_tp1():
    bars = [_c(0, 100.1, 101.6, 100.1, 101.4), _c(1, 101.4, 101.5, 99.8, 100.0)]
    sim = simulate_trade(
        side="buy",
        entry=100,
        stop=99,
        tp1=101.5,
        tp2=103,
        tp1_r=1.5,
        tp2_r=3.0,
        bars=bars,
        max_holding_bars=6,
        apply_spread=False,
    )
    assert sim["exitReason"] == "breakeven"
    assert sim["pnlR"] == pytest.approx(0.75, abs=0.01)


def test_slippage_applied():
    assert apply_slippage("buy", 2000.0) == 2000.0 + SLIPPAGE
    assert apply_slippage("sell", 2000.0) == 2000.0 - SLIPPAGE


def test_spread_cost_applied():
    bars = [_c(0, 100, 100.2, 98.9, 99.0)]
    with_cost = simulate_trade(
        side="buy", entry=100, stop=99, tp1=101.5, tp2=103, tp1_r=1.5, tp2_r=3.0, bars=bars, max_holding_bars=2, apply_spread=True
    )
    raw = simulate_trade(
        side="buy", entry=100, stop=99, tp1=101.5, tp2=103, tp1_r=1.5, tp2_r=3.0, bars=bars, max_holding_bars=2, apply_spread=False
    )
    assert with_cost["pnlR"] == pytest.approx(raw["pnlR"] - SPREAD_COST / 1.0, abs=0.001)


@pytest.mark.asyncio
async def test_strategy_filter_works(seeded_warehouse):
    report = await BacktestEngine().run(
        timeframe="M15",
        strategy_id="gold_breakout",
        days=30,
        candles=seeded_warehouse,
        min_rr=1.0,
    )
    assert all(t.strategyId == "gold_breakout" for t in report.trades)
    assert report.strategyId == "gold_breakout"


@pytest.mark.asyncio
async def test_report_saved_to_db(seeded_warehouse):
    reset_backtest_memory()
    report = await BacktestEngine().run(
        timeframe="M15", days=30, candles=seeded_warehouse, min_rr=1.0, persist=True
    )
    assert report.id
    stored = await get_report(report.id)
    assert stored and stored["id"] == report.id


@pytest.mark.asyncio
async def test_api_endpoint_runs_backtest(client, auth_header):
    resp = client.post(
        "/api/backtest/run",
        headers=auth_header,
        json={"timeframe": "M15", "strategyId": "gold_scalp", "days": 1, "minRr": 1.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "totalTrades" in body
    assert "candlesTested" in body
    listed = client.get("/api/backtest/reports", headers=auth_header)
    assert listed.status_code == 200


def test_timeout_exit():
    bars = [_c(0, 100.0, 100.3, 99.8, 100.1), _c(1, 100.1, 100.2, 99.9, 100.05)]
    sim = simulate_trade(
        side="buy",
        entry=100,
        stop=99,
        tp1=101.5,
        tp2=103,
        tp1_r=1.5,
        tp2_r=3.0,
        bars=bars,
        max_holding_bars=2,
        apply_spread=False,
    )
    assert sim["exitReason"] == "timeout"
    assert sim["barsHeld"] == 2


def test_max_drawdown_calculated():
    trades = [_trade(pnlR=-1), _trade(pnlR=-1.5), _trade(pnlR=0.4)]
    assert max_drawdown_r(trades) == pytest.approx(2.5)
    assert profit_factor(trades) == pytest.approx(0.4 / 2.5)


def test_by_session_stats():
    london = _trade(entryTime=datetime(2025, 3, 3, 9, tzinfo=timezone.utc), pnlR=1)
    asia = _trade(entryTime=datetime(2025, 3, 3, 2, tzinfo=timezone.utc), pnlR=-1)
    grouped = _group_session([london, asia])
    assert grouped["london"]["trades"] == 1
    assert grouped["asian"]["trades"] == 1


def test_by_month_stats():
    a = _trade(entryTime=datetime(2025, 1, 10, tzinfo=timezone.utc))
    b = _trade(entryTime=datetime(2025, 2, 10, tzinfo=timezone.utc))
    grouped = _group_month([a, b])
    assert grouped["2025-01"]["trades"] == 1
    assert grouped["2025-02"]["trades"] == 1


def test_rules_are_gold_warehouse_only():
    assert set(STRATEGY_RULES) == {
        "gold_liquidity_sniper",
        "gold_breakout",
        "gold_trend_follow",
        "gold_reversal",
        "gold_scalp",
    }
    for meta in STRATEGY_RULES.values():
        assert all(tf in {"M15", "H1", "H4", "D"} for tf in meta["timeframes"])
        assert "M1" not in meta["timeframes"] and "M5" not in meta["timeframes"]
