"""Ten candlestick notes for gold. Reliability is win-rate from pattern_memory."""

from __future__ import annotations

from typing import Any

from app.schemas import OHLCV
from app.services.trading_bot.candles import load_gold_candles
from app.services.trading_bot.multi_strategy_agent import atr, calculate_stop, targets
from app.services.trading_bot.store import get_pattern, signal_payload

GOLD = "XAU_USD"

PATTERNS = {
    "engulfing": "ابتلاع شرائي/بيعي",
    "pin_bar": "بين بار",
    "doji": "دوجي",
    "three_white_soldiers": "ثلاثة جنود بيض",
    "three_black_crows": "ثلاثة غربان سود",
    "inside_bar": "بار داخلي",
    "outside_bar": "بار خارجي",
    "hammer": "مطرقة",
    "shooting_star": "شهاب",
    "morning_evening_star": "نجمة الصباح/المساء",
}


def _body(c: OHLCV) -> float:
    return abs(c.close - c.open)


def _bull(c: OHLCV) -> bool:
    return c.close > c.open


def detect_engulfing(candles: list[OHLCV]) -> dict[str, Any] | None:
    if len(candles) < 2:
        return None
    a, b = candles[-2], candles[-1]
    if _bull(b) and not _bull(a) and b.open <= a.close and b.close >= a.open:
        return {"pattern": "engulfing", "side": "buy"}
    if not _bull(b) and _bull(a) and b.open >= a.close and b.close <= a.open:
        return {"pattern": "engulfing", "side": "sell"}
    return None


def detect_pin_bar(candles: list[OHLCV]) -> dict[str, Any] | None:
    if not candles:
        return None
    c = candles[-1]
    rng = max(c.high - c.low, 1e-9)
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    if lower / rng >= 0.6 and _body(c) / rng <= 0.35:
        return {"pattern": "pin_bar", "side": "buy"}
    if upper / rng >= 0.6 and _body(c) / rng <= 0.35:
        return {"pattern": "pin_bar", "side": "sell"}
    return None


def detect_doji(candles: list[OHLCV]) -> dict[str, Any] | None:
    if not candles:
        return None
    c = candles[-1]
    rng = max(c.high - c.low, 1e-9)
    if _body(c) / rng <= 0.12:
        return {"pattern": "doji", "side": "buy" if _bull(c) else "sell"}
    return None


def detect_three_white_soldiers(candles: list[OHLCV]) -> dict[str, Any] | None:
    if len(candles) < 3:
        return None
    trip = candles[-3:]
    if all(_bull(c) for c in trip) and trip[0].close < trip[1].close < trip[2].close:
        return {"pattern": "three_white_soldiers", "side": "buy"}
    return None


def detect_three_black_crows(candles: list[OHLCV]) -> dict[str, Any] | None:
    if len(candles) < 3:
        return None
    trip = candles[-3:]
    if all(not _bull(c) for c in trip) and trip[0].close > trip[1].close > trip[2].close:
        return {"pattern": "three_black_crows", "side": "sell"}
    return None


def detect_inside_bar(candles: list[OHLCV]) -> dict[str, Any] | None:
    if len(candles) < 2:
        return None
    a, b = candles[-2], candles[-1]
    if b.high <= a.high and b.low >= a.low:
        return {"pattern": "inside_bar", "side": "buy" if _bull(a) else "sell"}
    return None


def detect_outside_bar(candles: list[OHLCV]) -> dict[str, Any] | None:
    if len(candles) < 2:
        return None
    a, b = candles[-2], candles[-1]
    if b.high >= a.high and b.low <= a.low:
        return {"pattern": "outside_bar", "side": "buy" if _bull(b) else "sell"}
    return None


def detect_hammer(candles: list[OHLCV]) -> dict[str, Any] | None:
    if not candles:
        return None
    c = candles[-1]
    rng = max(c.high - c.low, 1e-9)
    lower = min(c.open, c.close) - c.low
    upper = c.high - max(c.open, c.close)
    if lower / rng >= 0.55 and upper / rng <= 0.2:
        return {"pattern": "hammer", "side": "buy"}
    return None


def detect_shooting_star(candles: list[OHLCV]) -> dict[str, Any] | None:
    if not candles:
        return None
    c = candles[-1]
    rng = max(c.high - c.low, 1e-9)
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    if upper / rng >= 0.55 and lower / rng <= 0.2:
        return {"pattern": "shooting_star", "side": "sell"}
    return None


def detect_morning_evening_star(candles: list[OHLCV]) -> dict[str, Any] | None:
    if len(candles) < 3:
        return None
    a, b, c = candles[-3:]
    small = _body(b) <= _body(a) * 0.45
    if not small:
        return None
    if not _bull(a) and _bull(c) and c.close > (a.open + a.close) / 2:
        return {"pattern": "morning_evening_star", "side": "buy"}
    if _bull(a) and not _bull(c) and c.close < (a.open + a.close) / 2:
        return {"pattern": "morning_evening_star", "side": "sell"}
    return None


DETECTORS = [
    detect_engulfing,
    detect_pin_bar,
    detect_doji,
    detect_three_white_soldiers,
    detect_three_black_crows,
    detect_inside_bar,
    detect_outside_bar,
    detect_hammer,
    detect_shooting_star,
    detect_morning_evening_star,
]


def detect(candles: list[OHLCV]) -> dict[str, Any] | None:
    for fn in DETECTORS:
        hit = fn(candles)
        if hit:
            return hit
    return None


def detect_all(candles: list[OHLCV]) -> list[dict[str, Any]]:
    hits = []
    for fn in DETECTORS:
        hit = fn(candles)
        if hit:
            hits.append(hit)
    return hits


async def calculate_reliability(pattern: str, timeframe: str) -> float:
    memory = await get_pattern(pattern, timeframe)
    if not memory or not memory.get("occurrences"):
        return 0.55
    return max(0.15, min(0.95, float(memory.get("winRate") or 0.55)))


class PatternNotesAgent:
    def __init__(self, candle_source=None, timeframe: str = "M15"):
        self.candle_source = candle_source
        self.timeframe = timeframe

    async def _candles(self, timeframe: str, count: int = 80) -> list[OHLCV]:
        if self.candle_source is not None:
            return await self.candle_source(GOLD, timeframe, count)
        return await load_gold_candles(timeframe, count)

    async def detect_patterns(self) -> list[dict[str, Any]]:
        candles = await self._candles(self.timeframe)
        if len(candles) < 5:
            return []
        hits = detect_all(candles)
        out: list[dict[str, Any]] = []
        last = candles[-1]
        for hit in hits:
            side = hit["side"]
            stop = calculate_stop(candles, side, atr(candles))
            tp1, tp2, rr = targets(last.close, stop, side)
            reliability = await calculate_reliability(hit["pattern"], self.timeframe)
            out.append(
                signal_payload(
                    agent_type="pattern_notes",
                    strategy_id=hit["pattern"],
                    timeframe=self.timeframe,
                    signal_type=side,
                    entry=round(last.close, 3),
                    stop=round(stop, 3),
                    tp1=tp1,
                    tp2=tp2,
                    confidence=reliability,
                    risk_reward=rr,
                    extra={"pattern": hit["pattern"], "label": PATTERNS.get(hit["pattern"], hit["pattern"])},
                )
            )
        return out
