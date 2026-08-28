from __future__ import annotations

from app.services.analysis import analyze_structure, build_recommendation
from app.services.simulator import generate_candles
from app.schemas import TradeRecommendation, OHLCV
from datetime import datetime, timezone


def _c(ts, o, h, l, c, i=0):
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return OHLCV(time=dt, timestamp=ts, open=o, high=h, low=l, close=c, volume=100, complete=True)


def test_bullish_fvg_detected():
    # Build a clear 3-candle bullish FVG: candle0 high 10, candle2 low 12
    base = 1_700_000_000_000
    candles = []
    price = 100.0
    for i in range(30):
        candles.append(_c(base + i * 60_000, price, price + 0.4, price - 0.4, price + 0.1, i))
        price += 0.1
    # inject FVG
    candles[20] = _c(base + 20 * 60_000, 102.0, 102.2, 101.8, 102.1)
    candles[21] = _c(base + 21 * 60_000, 102.1, 104.0, 102.0, 103.8)
    candles[22] = _c(base + 22 * 60_000, 103.9, 104.4, 103.7, 104.2)
    report = analyze_structure(candles)
    assert any(f.direction == "bullish" for f in report.fvgs)


def test_recommendation_schema_and_overlays():
    candles = generate_candles("XAU_USD", "M15", 200)
    rec = build_recommendation("XAU_USD", "15m", candles, htf_bias="BULLISH")
    dumped = rec.model_dump()
    TradeRecommendation.model_validate(dumped)
    assert rec.tradeSetup.entryPrice > 0
    assert rec.tradeSetup.stopLoss > 0
    assert rec.klineOverlays
    names = {o.name for o in rec.klineOverlays}
    assert "priceLine" in names
    assert rec.tradeSetup.riskRewardRatio >= 1.5


def test_simulator_candle_monotonic_time():
    candles = generate_candles("EUR_USD", "H1", 50)
    ts = [c.timestamp for c in candles]
    assert ts == sorted(ts)
    assert all(c.high >= max(c.open, c.close) for c in candles)
    assert all(c.low <= min(c.open, c.close) for c in candles)
