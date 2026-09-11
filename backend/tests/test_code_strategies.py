"""Python-code strategies: sandbox, lint, engine, library roundtrip."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import OHLCV
from app.services.backtest.engine import BacktestEngine
from app.services.trading_bot.code_runner import (
    lint_code,
    run_code_backtest,
    run_code_on_window,
)
from app.services.trading_bot.strategy_library import get_library, reset_library
from app.services.trading_bot.strategy_schema import StrategyRule

MA_CROSS_CODE = """
def _sma(candles, n, offset=0):
    end = len(candles) - offset
    total = 0.0
    for k in range(end - n, end):
        total += candles[k]["close"]
    return total / n


def on_bar(ctx):
    if ctx.i < 25:
        return None
    fast = _sma(ctx.candles, 5)
    slow = _sma(ctx.candles, 20)
    prev_fast = _sma(ctx.candles, 5, 1)
    prev_slow = _sma(ctx.candles, 20, 1)
    last = ctx.candles[-1]
    if prev_fast <= prev_slow and fast > slow:
        entry = last["close"]
        return {"action": "BUY", "entry": entry, "stopLoss": entry - 3.0, "tp1": entry + 3.0, "tp2": entry + 6.0, "note": "cross up"}
    if prev_fast >= prev_slow and fast < slow:
        entry = last["close"]
        return {"action": "SELL", "entry": entry, "stopLoss": entry + 3.0, "tp1": entry - 3.0, "tp2": None}
    return None
"""


def synthetic_candles(n: int = 400) -> list[OHLCV]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out: list[OHLCV] = []
    for i in range(n):
        o = 2000.0 + 10.0 * math.sin(i / 12.0)
        c = 2000.0 + 10.0 * math.sin((i + 1) / 12.0)
        t = base + timedelta(minutes=15 * i)
        out.append(
            OHLCV(
                time=t,
                timestamp=int(t.timestamp()),
                open=round(o, 3),
                high=round(max(o, c) + 1.5, 3),
                low=round(min(o, c) - 1.5, 3),
                close=round(c, 3),
                volume=100,
            )
        )
    return out


def klines(candles: list[OHLCV]) -> list[dict]:
    return [c.to_kline() for c in candles]


@pytest.fixture(autouse=True)
async def _clean_lab(monkeypatch):
    import app.services.trading_bot.strategy_library as lab

    reset_library()
    monkeypatch.setattr(lab, "SessionLocal", None)
    yield
    reset_library()


def test_lint_catches_syntax_error():
    result = lint_code("def on_bar(ctx:\n    return None")
    assert result["ok"] is False
    assert "syntax" in result["error"].lower()


def test_lint_requires_on_bar():
    result = lint_code("x = 1")
    assert result["ok"] is False
    assert "on_bar" in result["error"]


def test_lint_ok_and_empty():
    assert lint_code(MA_CROSS_CODE)["ok"] is True
    assert lint_code("")["ok"] is False


def test_ma_cross_produces_signals():
    result = run_code_backtest(MA_CROSS_CODE, klines(synthetic_candles()), {})
    assert result["ok"] is True
    signals = result["signals"]
    assert len(signals) >= 4
    actions = {s["action"] for s in signals}
    assert actions == {"BUY", "SELL"}
    for sig in signals:
        assert 25 <= sig["index"] < 400
        assert isinstance(sig["entry"], float)
        assert isinstance(sig["stopLoss"], float)


def test_sandbox_blocks_import_socket():
    code = "import socket\n\ndef on_bar(ctx):\n    return None\n"
    result = run_code_backtest(code, klines(synthetic_candles(30)), {})
    assert result["ok"] is False
    assert "not allowed" in result["error"]
    # server process is still alive and can run more code afterwards
    assert run_code_backtest(MA_CROSS_CODE, klines(synthetic_candles(60)), {})["ok"] is True


def test_sandbox_blocks_open():
    code = "def on_bar(ctx):\n    open('/etc/passwd')\n    return None\n"
    result = run_code_backtest(code, klines(synthetic_candles(5)), {})
    assert result["ok"] is False
    assert "open" in result["error"]


def test_sandbox_blocks_os_via_import():
    code = "def on_bar(ctx):\n    import os\n    return None\n"
    result = run_code_backtest(code, klines(synthetic_candles(5)), {})
    assert result["ok"] is False
    assert "not allowed" in result["error"]


def test_timeout_kills_infinite_loop():
    code = "def on_bar(ctx):\n    while True:\n        pass\n"
    result = run_code_backtest(
        code,
        klines(synthetic_candles(5)),
        {},
        cpu_seconds=1,
        wall_seconds=5,
    )
    assert result["ok"] is False
    assert "limit" in result["error"] or "timeout" in result["error"]


def test_run_code_on_window_last_bar_only():
    candles = synthetic_candles(120)
    sig = run_code_on_window(MA_CROSS_CODE, klines(candles), {})
    # signal only when the cross happens exactly on the final bar
    full = run_code_backtest(MA_CROSS_CODE, klines(candles), {})
    last_idx = len(candles) - 1
    expected = next((s for s in full["signals"] if s["index"] == last_idx), None)
    assert sig == expected


async def test_python_strategy_roundtrips_library():
    lib = get_library()
    created = await lib.propose(
        {
            "name": "MA cross code play",
            "description": "python strategy",
            "timeframes": ["M15"],
            "kind": "python",
            "code": MA_CROSS_CODE,
        }
    )
    assert created["ok"] is True
    sid = created["strategy"]["id"]
    rule = await lib.get(sid)
    assert rule is not None
    assert rule.kind == "python"
    assert rule.code == MA_CROSS_CODE
    assert rule.status == "draft"
    # JSON roundtrip preserves kind/code (what _persist stores)
    again = StrategyRule.model_validate(rule.model_dump(mode="json"))
    assert again.kind == "python" and again.code == MA_CROSS_CODE


async def test_propose_rejects_broken_code():
    lib = get_library()
    created = await lib.propose({"name": "Broken code", "kind": "python", "code": "def on_bar(ctx:"})
    assert created["ok"] is False
    assert "Code rejected" in created["detail"]


async def test_engine_runs_python_strategy_end_to_end():
    rule = StrategyRule(
        id="py_ma_cross",
        name="MA cross python",
        timeframes=["M15"],
        kind="python",
        code=MA_CROSS_CODE,
        tp1_r=1.0,
        tp2_r=2.0,
        max_holding_bars=24,
    )
    report = await BacktestEngine().run(
        timeframe="M15",
        strategy_id="py_ma_cross",
        candles=synthetic_candles(400),
        rule=rule,
        min_rr=0.5,
    )
    assert report.totalTrades > 0
    assert "py_ma_cross" in report.byStrategy
    assert report.byStrategy["py_ma_cross"]["trades"] == report.totalTrades
    for trade in report.trades:
        assert trade.strategyId == "py_ma_cross"
        assert trade.direction in {"buy", "sell"}
        assert trade.entryPrice > 0 and trade.stopLoss > 0
    # trades are chronological
    times = [t.entryTime for t in report.trades]
    assert times == sorted(times)


async def test_lint_route():
    from app.api import routes

    ok = await routes.strategies_lint_code({"code": MA_CROSS_CODE})
    assert ok["ok"] is True
    bad = await routes.strategies_lint_code({"code": "def on_bar(ctx:"})
    assert bad["ok"] is False and bad["error"]


def test_mcp_propose_schema_accepts_code():
    from app.services.mcp_tools import mcp_tool_specs

    spec = next(s for s in mcp_tool_specs() if s["name"] == "propose_strategy")
    props = spec["input_schema"]["properties"]
    assert "kind" in props and "code" in props


async def test_mcp_propose_python_strategy():
    from app.services.mcp_tools import dispatch_tool

    result = await dispatch_tool(
        "propose_strategy",
        {"name": "Claude code play", "kind": "python", "code": MA_CROSS_CODE, "timeframes": ["H1"]},
    )
    assert result["ok"] is True
    assert result["strategy"]["kind"] == "python"
    assert result["strategy"]["code"] == MA_CROSS_CODE
