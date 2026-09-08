"""Five gold-only ICT strategies. Signals still pass the hard risk gate."""

from __future__ import annotations

from typing import Any, Callable

from app.schemas import OHLCV
from app.services.analysis import StructureReport, analyze_structure
from app.services.trading_bot.candles import load_gold_candles
from app.services.trading_bot.store import signal_payload

GOLD = "XAU_USD"

STRATEGIES = {
    "gold_liquidity_sniper": {
        "name": "قناص سيولة الذهب",
        "timeframes": ["M5", "M15"],
        "description": "كنس سيولة آسيا ثم ارتداد من FVG",
    },
    "gold_breakout": {
        "name": "كسر نطاق الذهب",
        "timeframes": ["M15", "H1"],
        "description": "كسر نطاق آسيا مع إعادة اختبار",
    },
    "gold_trend_follow": {
        "name": "تتبع اتجاه الذهب",
        "timeframes": ["H1", "H4"],
        "description": "الدخول مع اتجاه H4 عند FVG/OB",
    },
    "gold_reversal": {
        "name": "انعكاس الذهب",
        "timeframes": ["M15", "H1"],
        "description": "انعكاس عند مناطق عرض/طلب قوية",
    },
    "gold_scalp": {
        "name": "سكالبينج الذهب",
        "timeframes": ["M1", "M5"],
        "description": "صفقات سريعة مع وقف ضيق",
    },
}


def atr(candles: list[OHLCV], period: int = 14) -> float:
    window = candles[-period:] if candles else []
    if not window:
        return 1.0
    return max(sum(c.high - c.low for c in window) / len(window), 0.05)


def targets(entry: float, stop: float, side: str) -> tuple[float, float, float]:
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(abs(entry) * 0.001, 0.1)
    if side == "buy":
        tp1, tp2 = entry + 1.5 * risk, entry + 3.0 * risk
    else:
        tp1, tp2 = entry - 1.5 * risk, entry - 3.0 * risk
    rr = abs(tp2 - entry) / risk
    return round(tp1, 3), round(tp2, 3), round(rr, 2)


def _side_from_bias(bias: str, fallback: str = "buy") -> str:
    if bias == "BEARISH":
        return "sell"
    if bias == "BULLISH":
        return "buy"
    return fallback


def _aligned_fvg(report: StructureReport, side: str):
    want = "bullish" if side == "buy" else "bearish"
    matches = [f for f in report.fvgs if f.direction == want]
    return matches[-1] if matches else None


def _aligned_ob(report: StructureReport, side: str):
    want = "bullish" if side == "buy" else "bearish"
    matches = [b for b in report.order_blocks if b.direction == want]
    return matches[-1] if matches else None


def calculate_entry(candles: list[OHLCV], report: StructureReport, side: str) -> float:
    fvg = _aligned_fvg(report, side)
    if fvg:
        return (fvg.low + fvg.high) / 2
    ob = _aligned_ob(report, side)
    if ob:
        return (ob.low + ob.high) / 2
    last = candles[-1]
    pad = atr(candles) * 0.15
    return last.close - pad if side == "buy" else last.close + pad


def calculate_stop(candles: list[OHLCV], side: str, range_atr: float | None = None) -> float:
    last = candles[-1]
    pad = (range_atr if range_atr is not None else atr(candles)) * 0.8
    if side == "buy":
        swing = min(c.low for c in candles[-8:])
        return min(swing, last.close) - pad * 0.25
    swing = max(c.high for c in candles[-8:])
    return max(swing, last.close) + pad * 0.25


def calculate_confidence(flags: list[bool]) -> float:
    if not flags:
        return 0.0
    return round(sum(1 for f in flags if f) / len(flags), 3)


def check_liquidity_sniper(candles: list[OHLCV], report: StructureReport) -> bool:
    if not report.liquidity_sweep:
        return False
    side = "buy" if "BUY" in (report.liquidity_sweep or "") else "sell"
    return _aligned_fvg(report, side) is not None or bool(report.fvgs)


def check_breakout(candles: list[OHLCV], report: StructureReport) -> bool:
    if len(candles) < 3:
        return False
    last, prev = candles[-1], candles[-2]
    broke_high = last.close > report.asian_high and prev.close <= report.asian_high
    broke_low = last.close < report.asian_low and prev.close >= report.asian_low
    return bool(broke_high or broke_low)


def check_trend_follow(candles: list[OHLCV], report: StructureReport) -> bool:
    if report.bias not in {"BULLISH", "BEARISH"}:
        return False
    side = _side_from_bias(report.bias)
    return _aligned_fvg(report, side) is not None or _aligned_ob(report, side) is not None


def check_reversal(candles: list[OHLCV], report: StructureReport) -> bool:
    if len(candles) < 3:
        return False
    last = candles[-1]
    body = abs(last.close - last.open)
    wick_up = last.high - max(last.close, last.open)
    wick_dn = min(last.close, last.open) - last.low
    rejection = wick_up > body * 1.4 or wick_dn > body * 1.4
    return rejection and bool(report.order_blocks)


def check_scalp(candles: list[OHLCV], report: StructureReport) -> bool:
    if len(candles) < 2:
        return False
    last = candles[-1]
    body = abs(last.close - last.open)
    rng = max(last.high - last.low, 0.01)
    impulse = body / rng >= 0.55
    return impulse and report.bias in {"BULLISH", "BEARISH"}


CHECKERS: dict[str, Callable[[list[OHLCV], StructureReport], bool]] = {
    "gold_liquidity_sniper": check_liquidity_sniper,
    "gold_breakout": check_breakout,
    "gold_trend_follow": check_trend_follow,
    "gold_reversal": check_reversal,
    "gold_scalp": check_scalp,
}


def build_strategy_signal(
    strategy_id: str,
    candles: list[OHLCV],
    report: StructureReport,
    timeframe: str,
) -> dict[str, Any] | None:
    checker = CHECKERS.get(strategy_id)
    if checker is None or not candles:
        return None
    ok = checker(candles, report)
    if not ok:
        return None
    if strategy_id == "gold_breakout":
        side = "buy" if candles[-1].close > report.asian_high else "sell"
        flags = [True, report.bias != "NEUTRAL", bool(report.last_bos)]
    elif strategy_id == "gold_liquidity_sniper":
        side = "buy" if "BUY" in (report.liquidity_sweep or "") else "sell"
        flags = [True, bool(report.fvgs), report.bias != "NEUTRAL"]
    elif strategy_id == "gold_reversal":
        last = candles[-1]
        wick_up = last.high - max(last.close, last.open)
        wick_dn = min(last.close, last.open) - last.low
        side = "sell" if wick_up > wick_dn else "buy"
        flags = [True, bool(report.order_blocks), True]
    else:
        side = _side_from_bias(report.bias)
        flags = [True, report.bias in {"BULLISH", "BEARISH"}, bool(report.fvgs or report.order_blocks)]
    entry = calculate_entry(candles, report, side)
    stop = calculate_stop(candles, side)
    tp1, tp2, rr = targets(entry, stop, side)
    return signal_payload(
        agent_type="multi_strategy",
        strategy_id=strategy_id,
        timeframe=timeframe,
        signal_type=side,
        entry=round(entry, 3),
        stop=round(stop, 3),
        tp1=tp1,
        tp2=tp2,
        confidence=calculate_confidence(flags),
        risk_reward=rr,
        extra={"confluence": list(report.confluence), "bias": report.bias},
    )


class MultiStrategyAgent:
    def __init__(self, candle_source=None, active: list[str] | None = None):
        self.candle_source = candle_source
        self.active = list(active or STRATEGIES.keys())

    async def _candles(self, timeframe: str, count: int = 180) -> list[OHLCV]:
        if self.candle_source is not None:
            return await self.candle_source(GOLD, timeframe, count)
        return await load_gold_candles(timeframe, count)

    async def scan_xau_usd(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        seen: set[str] = set()
        for strategy_id in self.active:
            meta = STRATEGIES.get(strategy_id)
            if not meta:
                continue
            for tf in meta["timeframes"]:
                candles = await self._candles(tf)
                if len(candles) < 20:
                    continue
                report = analyze_structure(candles)
                sig = build_strategy_signal(strategy_id, candles, report, tf)
                if not sig:
                    continue
                key = f"{strategy_id}:{tf}:{sig['signalType']}"
                if key in seen:
                    continue
                seen.add(key)
                signals.append(sig)
        return signals
