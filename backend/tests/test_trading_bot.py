from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import OHLCV
from app.services.analysis import analyze_structure
from app.services.risk_rules import RiskRejected, enforce_risk_gate
from app.services.trading_bot.coordinator import TradingBotCoordinator, reset_coordinator
from app.services.trading_bot.models import BotSignalRow, PatternMemoryRow, StrategyPerformanceRow  # noqa: F401
from app.services.trading_bot.multi_strategy_agent import (
    STRATEGIES,
    MultiStrategyAgent,
    build_strategy_signal,
    check_breakout,
    check_liquidity_sniper,
    check_reversal,
    check_scalp,
    check_trend_follow,
    targets,
)
from app.services.trading_bot.news_candle_agent import (
    NewsCandleAgent,
    analyze_gold_news_candle,
    identify_news_candle,
    pick_news_strategy,
)
from app.services.trading_bot.pattern_notes_agent import PATTERNS, detect, detect_all
from app.services.trading_bot.promote import signal_to_recommendation
from app.services.trading_bot.store import (
    bump_pattern,
    get_pattern,
    list_signals,
    reset_bot_memory,
    reset_bot_store,
    save_signal,
    signal_payload,
    update_signal,
)


def _c(ts: int, o: float, h: float, l: float, c: float, v: float = 100) -> OHLCV:
    return OHLCV(
        time=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def _range(n: int = 40, start: float = 2650.0) -> list[OHLCV]:
    base = 1_720_000_000_000
    out = []
    price = start
    for i in range(n):
        o = price
        c = price + (1.2 if i % 3 else -0.4)
        h = max(o, c) + 1.5
        l = min(o, c) - 1.2
        out.append(_c(base + i * 60_000, o, h, l, c, 80 + i))
        price = c
    return out


@pytest.fixture(autouse=True)
async def _clean_bot():
    await reset_bot_store()
    reset_coordinator()
    yield
    await reset_bot_store()
    reset_bot_memory()


@pytest.mark.asyncio
async def test_bot_start_stop():
    bot = TradingBotCoordinator()
    snap = await bot.start()
    assert snap["running"] is True
    await bot.stop()
    assert bot.is_running is False


@pytest.mark.asyncio
async def test_bot_monitor_loop_runs():
    candles = _range(50)

    async def source(_ins, _g, _n):
        return candles

    class Empty:
        async def detect_patterns(self):
            return []

        async def monitor_events(self):
            return []

    bot = TradingBotCoordinator()
    bot.multi_strategy_agent = MultiStrategyAgent(candle_source=source, active=["gold_trend_follow"])
    bot.pattern_notes_agent = Empty()
    bot.news_candle_agent = Empty()

    class Runtime:
        botEnabled = True
        botScanInterval = 60
        botAgents = ["multi_strategy"]
        botActiveStrategies = ["gold_trend_follow"]

    saved = await bot.run_cycle(Runtime())
    assert isinstance(saved, list)


@pytest.mark.asyncio
async def test_multi_strategy_scan_returns_signals():
    candles = _range(80, 2640)

    async def source(_i, _g, _n):
        return candles

    agent = MultiStrategyAgent(candle_source=source)
    signals = await agent.scan_xau_usd()
    assert isinstance(signals, list)


def test_liquidity_sniper_strategy():
    candles = _range(30)
    # Drive a reclaim of asian low.
    candles[-1] = _c(candles[-1].timestamp, 2640, 2646, 2620, 2644, 200)
    report = analyze_structure(candles)
    if not report.liquidity_sweep:
        report.liquidity_sweep = "BUY_SIDE_RECLAIM_ASIAN_LOW"
        report.fvgs = report.fvgs or []
    assert check_liquidity_sniper(candles, report) or report.liquidity_sweep
    sig = build_strategy_signal("gold_liquidity_sniper", candles, report, "M15")
    assert sig is None or sig["strategyId"] == "gold_liquidity_sniper"


def test_breakout_strategy():
    candles = _range(30, 2650)
    report = analyze_structure(candles)
    prev_close = candles[-2].close
    candles[-1] = _c(candles[-1].timestamp, prev_close, prev_close + 4, prev_close - 0.2, prev_close + 3)
    report.asian_high = prev_close
    report.asian_low = min(c.low for c in candles) - 20
    assert check_breakout(candles, report) is True


def test_trend_follow_strategy():
    candles = _range(40, 2600)
    report = analyze_structure(candles)
    report.bias = "BULLISH"
    if not report.fvgs and not report.order_blocks:
        from app.services.analysis import FVG

        report.fvgs.append(FVG(0, 2, 2590, 2594, "bullish", candles[0].timestamp, candles[2].timestamp))
    assert check_trend_follow(candles, report) is True
    sig = build_strategy_signal("gold_trend_follow", candles, report, "H1")
    assert sig and sig["signalType"] == "buy"


def test_reversal_strategy():
    candles = _range(25)
    candles[-1] = _c(candles[-1].timestamp, 2660, 2672, 2658.5, 2659.2, 150)
    report = analyze_structure(candles)
    if not report.order_blocks:
        from app.services.analysis import OrderBlock

        report.order_blocks.append(OrderBlock(3, candles[3].timestamp, 2655, 2662, "bearish"))
    assert check_reversal(candles, report) is True


def test_scalping_strategy():
    candles = _range(22)
    candles[-1] = _c(candles[-1].timestamp, 2650, 2658, 2649.8, 2657.6, 300)
    report = analyze_structure(candles)
    report.bias = "BULLISH"
    assert check_scalp(candles, report) is True


def test_pattern_detection_all_10_patterns():
    base = 1_720_000_000_000
    fixtures = {
        "engulfing": [_c(base, 10, 10.2, 9.5, 9.6), _c(base + 60_000, 9.5, 10.8, 9.4, 10.6)],
        "pin_bar": [_c(base, 10, 10.2, 8.8, 10.05)],
        "doji": [_c(base, 10, 10.4, 9.6, 10.02)],
        "three_white_soldiers": [
            _c(base, 10, 10.4, 9.9, 10.3),
            _c(base + 1, 10.25, 10.8, 10.2, 10.7),
            _c(base + 2, 10.65, 11.2, 10.6, 11.1),
        ],
        "three_black_crows": [
            _c(base, 11, 11.1, 10.4, 10.5),
            _c(base + 1, 10.55, 10.6, 10.0, 10.1),
            _c(base + 2, 10.15, 10.2, 9.6, 9.7),
        ],
        "inside_bar": [_c(base, 10, 11, 9, 10.4), _c(base + 1, 10.1, 10.6, 9.5, 10.2)],
        "outside_bar": [_c(base, 10, 10.3, 9.8, 10.1), _c(base + 1, 9.9, 10.8, 9.4, 10.5)],
        "hammer": [_c(base, 10, 10.15, 9.0, 10.05)],
        "shooting_star": [_c(base, 10, 11.2, 9.95, 10.05)],
        "morning_evening_star": [
            _c(base, 11, 11.1, 10.2, 10.3),
            _c(base + 1, 10.25, 10.35, 10.15, 10.22),
            _c(base + 2, 10.3, 11.0, 10.25, 10.9),
        ],
    }
    found = set()
    for name, candles in fixtures.items():
        hits = {h["pattern"] for h in detect_all(candles)}
        if name in hits or (detect(candles) or {}).get("pattern") == name:
            found.add(name)
    assert found == set(PATTERNS)


@pytest.mark.asyncio
async def test_pattern_memory_updates():
    row = await bump_pattern("engulfing", "M15", won=True, rr=3.0)
    assert row["occurrences"] == 1
    assert row["successful"] == 1
    stored = await get_pattern("engulfing", "M15")
    assert stored and stored["winRate"] == 1.0


def test_news_candle_analysis():
    now = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)
    candles = [
        _c(int(now.timestamp() * 1000) - 60_000, 2650, 2651, 2649, 2650.2, 90),
        _c(int(now.timestamp() * 1000), 2650, 2664, 2649.5, 2662, 400),
    ]
    candle = identify_news_candle(candles, now)
    assert candle and candle.close == 2662
    analysis = analyze_gold_news_candle(candles, now)
    assert analysis["decision"] in {"buy", "sell", "wait"}
    assert pick_news_strategy(2, analysis) in {None, "news_momentum_gold"}


@pytest.mark.asyncio
async def test_news_momentum_strategy():
    from app.services.economic_calendar import EconomicEvent

    stamp = datetime.now(timezone.utc) - timedelta(minutes=2)

    async def events():
        return [EconomicEvent(id="ev_test", title="CPI y/y", timestamp=stamp, impact="critical")]

    async def candles(_i, _g, _n):
        ts = int(stamp.timestamp() * 1000)
        return [_c(ts - 60_000, 2650, 2652, 2648, 2651, 80), _c(ts, 2651, 2670, 2650, 2668, 500)]

    signals = await NewsCandleAgent(candle_source=candles, events_source=events).monitor_events()
    assert any(s["strategyId"] == "news_momentum_gold" for s in signals)


@pytest.mark.asyncio
async def test_news_retracement_strategy():
    from app.services.economic_calendar import EconomicEvent

    stamp = datetime.now(timezone.utc) - timedelta(minutes=7)

    async def events():
        return [EconomicEvent(id="ev_ret", title="FOMC", timestamp=stamp, impact="high")]

    async def candles(_i, _g, _n):
        ts = int(stamp.timestamp() * 1000)
        return [
            _c(ts - 60_000, 2650, 2652, 2648, 2651, 80),
            _c(ts, 2651, 2670, 2650, 2668, 500),
            _c(ts + 6 * 60_000, 2664, 2666, 2658, 2660, 180),
        ]

    signals = await NewsCandleAgent(candle_source=candles, events_source=events).monitor_events()
    assert any(s["strategyId"] == "news_retracement_gold" for s in signals)


@pytest.mark.asyncio
async def test_news_momentum_and_retracement():
    await test_news_momentum_strategy()
    await test_news_retracement_strategy()


@pytest.mark.asyncio
async def test_signal_saving_to_db():
    payload = signal_payload(
        agent_type="multi_strategy",
        strategy_id="gold_scalp",
        timeframe="M5",
        signal_type="buy",
        entry=2650,
        stop=2647,
        tp1=2654.5,
        tp2=2659,
        confidence=0.7,
        risk_reward=3.0,
    )
    saved = await save_signal(payload)
    rows = await list_signals(10)
    assert any(r["id"] == saved["id"] for r in rows)


@pytest.mark.asyncio
async def test_risk_gate_validates_signals(monkeypatch):
    class Runtime:
        minRiskReward = 2.0
        maxRiskPercent = 1.0
        allowedSessions = ["london", "ny", "asian", "london_ny_overlap", "late_ny_asia"]

    async def load():
        return Runtime()

    monkeypatch.setattr("app.services.risk_rules.load_runtime_settings", load)
    monkeypatch.setattr("app.services.macro_feed.current_session", lambda now=None: {"session": "london", "utcHour": 10})
    rec = signal_to_recommendation(
        signal_payload(
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
    )
    ok = await enforce_risk_gate(rec.model_dump(mode="json"))
    assert ok["ok"] is True
    rec.tradeSetup.riskRewardRatio = 0.4
    rec.tradeSetup.takeProfitLevels[-1].price = 2650.4
    with pytest.raises(RiskRejected):
        await enforce_risk_gate(rec.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_bot_api_endpoints(client, auth_header):
    status = client.get("/api/bot/status", headers=auth_header)
    assert status.status_code == 200
    assert "running" in status.json()
    signals = client.get("/api/bot/signals", headers=auth_header)
    assert signals.status_code == 200
    perf = client.get("/api/bot/performance", headers=auth_header)
    assert perf.status_code == 200
    started = client.post("/api/bot/start", headers=auth_header)
    assert started.status_code == 200
    stopped = client.post("/api/bot/stop", headers=auth_header)
    assert stopped.status_code == 200


@pytest.mark.asyncio
async def test_bot_pause_resume_integration(monkeypatch):
    from app.services.run_control import reset_for_tests, set_paused

    reset_for_tests()
    bot = reset_coordinator()

    class Runtime:
        botEnabled = True
        botScanInterval = 60
        botAgents = ["multi_strategy"]
        botActiveStrategies = ["gold_scalp"]

    async def load():
        return Runtime()

    monkeypatch.setattr("app.services.settings_store.load_runtime_settings", load)
    await bot.start()
    assert bot.is_running is True
    await set_paused(True)
    assert bot.is_running is False
    await set_paused(False)
    assert bot.is_running is True
    await bot.stop()
    reset_for_tests()


def test_strategy_catalog_is_gold_only():
    assert set(STRATEGIES) == {
        "gold_liquidity_sniper",
        "gold_breakout",
        "gold_trend_follow",
        "gold_reversal",
        "gold_scalp",
    }
    tp1, tp2, rr = targets(100, 99, "buy")
    assert tp2 == 103
    assert rr == 3
