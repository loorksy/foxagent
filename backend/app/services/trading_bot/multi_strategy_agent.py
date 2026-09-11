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


def generic_conditions(candles: list[OHLCV], report: StructureReport, conditions: dict[str, Any] | None) -> bool:
    conds = conditions or {}
    named = conds.get("checker")
    if named in CHECKERS and not CHECKERS[named](candles, report):
        return False
    flags: list[bool] = []
    if conds.get("asian_sweep"):
        flags.append(bool(report.liquidity_sweep))
    if conds.get("fvg_exists"):
        flags.append(bool(report.fvgs))
    if conds.get("bos_confirmed"):
        flags.append(bool(report.last_bos))
    if conds.get("breakout"):
        flags.append(check_breakout(candles, report))
    if conds.get("trend"):
        flags.append(check_trend_follow(candles, report))
    if conds.get("reversal") or conds.get("rejection"):
        flags.append(check_reversal(candles, report))
    if conds.get("impulse") or conds.get("scalp"):
        flags.append(check_scalp(candles, report))
    if not flags and named not in CHECKERS:
        return False
    return all(flags) if flags else True


def evaluate_rule(rule: Any, candles: list[OHLCV], report: StructureReport) -> bool:
    sid = getattr(rule, "id", None)
    if sid in CHECKERS:
        if not CHECKERS[sid](candles, report):
            return False
        extra = getattr(rule, "entry_conditions", None) or {}
        return generic_conditions(candles, report, extra) if extra else True
    return generic_conditions(candles, report, getattr(rule, "entry_conditions", None))


def infer_side(rule: Any, candles: list[OHLCV], report: StructureReport) -> str:
    direction = getattr(rule, "direction", "both")
    if direction in {"buy", "sell"}:
        return direction
    sid = getattr(rule, "id", "")
    if sid == "gold_breakout":
        return "buy" if candles[-1].close > report.asian_high else "sell"
    if sid == "gold_liquidity_sniper":
        return "buy" if "BUY" in (report.liquidity_sweep or "") else "sell"
    if sid == "gold_reversal":
        last = candles[-1]
        wick_up = last.high - max(last.close, last.open)
        wick_dn = min(last.close, last.open) - last.low
        return "sell" if wick_up > wick_dn else "buy"
    return _side_from_bias(report.bias)


def build_rule_signal(rule: Any, candles: list[OHLCV], report: StructureReport, timeframe: str) -> dict[str, Any] | None:
    if not candles or not evaluate_rule(rule, candles, report):
        return None
    sid = getattr(rule, "id", "custom")
    if sid in CHECKERS:
        return build_strategy_signal(sid, candles, report, timeframe)
    side = infer_side(rule, candles, report)
    entry = calculate_entry(candles, report, side)
    stop = calculate_stop(candles, side)
    tp1_r = float(getattr(rule, "tp1_r", 1.5) or 1.5)
    tp2_r = float(getattr(rule, "tp2_r", 3.0) or 3.0)
    risk = abs(entry - stop) or 0.1
    if side == "buy":
        tp1, tp2 = entry + tp1_r * risk, entry + tp2_r * risk
    else:
        tp1, tp2 = entry - tp1_r * risk, entry - tp2_r * risk
    return signal_payload(
        agent_type="multi_strategy",
        strategy_id=sid,
        timeframe=timeframe,
        signal_type=side,
        entry=round(entry, 3),
        stop=round(stop, 3),
        tp1=round(tp1, 3),
        tp2=round(tp2, 3),
        confidence=0.6,
        risk_reward=round(tp2_r, 2),
        extra={"confluence": list(report.confluence), "bias": report.bias, "source": getattr(rule, "source", "")},
    )


async def build_code_signal(rule: Any, candles: list[OHLCV], timeframe: str) -> dict[str, Any] | None:
    """Python-kind strategy: run the sandboxed code once on the latest window
    and emit a signal only if it fired on the LAST bar. Real candles only."""
    import asyncio

    from app.services.trading_bot.code_runner import run_code_on_window

    if not candles:
        return None
    klines = [c.to_kline() for c in candles]
    params = {
        "timeframe": timeframe,
        "direction": getattr(rule, "direction", "both"),
        "tp1_r": float(getattr(rule, "tp1_r", 1.5) or 1.5),
        "tp2_r": float(getattr(rule, "tp2_r", 3.0) or 3.0),
        "max_holding_bars": int(getattr(rule, "max_holding_bars", 48) or 48),
    }
    sig = await asyncio.to_thread(run_code_on_window, getattr(rule, "code", ""), klines, params)
    if not sig:
        return None
    side = "buy" if str(sig.get("action")) == "BUY" else "sell"
    direction = getattr(rule, "direction", "both")
    if direction in {"buy", "sell"} and side != direction:
        return None
    entry = float(sig.get("entry") or 0.0)
    stop = float(sig.get("stopLoss") or 0.0)
    if entry <= 0 or (side == "buy" and stop >= entry) or (side == "sell" and stop <= entry):
        return None
    risk = abs(entry - stop)
    tp1 = float(sig.get("tp1") or 0.0)
    if (side == "buy" and tp1 <= entry) or (side == "sell" and tp1 >= entry):
        tp1 = entry + params["tp1_r"] * risk if side == "buy" else entry - params["tp1_r"] * risk
    tp2_raw = sig.get("tp2")
    if tp2_raw is None:
        tp2 = entry + params["tp2_r"] * risk if side == "buy" else entry - params["tp2_r"] * risk
    else:
        tp2 = float(tp2_raw)
        if (side == "buy" and tp2 <= entry) or (side == "sell" and tp2 >= entry):
            tp2 = entry + params["tp2_r"] * risk if side == "buy" else entry - params["tp2_r"] * risk
    rr = abs(tp2 - entry) / risk if risk > 0 else 0.0
    return signal_payload(
        agent_type="multi_strategy",
        strategy_id=getattr(rule, "id", "custom"),
        timeframe=timeframe,
        signal_type=side,
        entry=round(entry, 3),
        stop=round(stop, 3),
        tp1=round(tp1, 3),
        tp2=round(tp2, 3),
        confidence=0.6,
        risk_reward=round(rr, 2),
        extra={"kind": "python", "note": str(sig.get("note") or ""), "source": getattr(rule, "source", "")},
    )


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
        self.active = list(active) if active is not None else None

    async def _candles(self, timeframe: str, count: int = 180) -> list[OHLCV]:
        if self.candle_source is not None:
            return await self.candle_source(GOLD, timeframe, count)
        return await load_gold_candles(timeframe, count)

    async def _rules(self):
        from app.services.trading_bot.strategy_library import get_library

        rules = await get_library().get_active_strategies()
        if self.active is None:
            return rules
        wanted = set(self.active)
        return [r for r in rules if r.id in wanted]

    async def scan_xau_usd(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        seen: set[str] = set()
        rules = await self._rules()
        for rule in rules:
            for tf in rule.timeframes:
                candles = await self._candles(tf)
                if len(candles) < 20:
                    continue
                if getattr(rule, "kind", "dsl") == "python":
                    sig = await build_code_signal(rule, candles, tf)
                else:
                    report = analyze_structure(candles)
                    sig = build_rule_signal(rule, candles, report, tf)
                if not sig:
                    continue
                key = f"{rule.id}:{tf}:{sig['signalType']}"
                if key in seen:
                    continue
                seen.add(key)
                signals.append(sig)
        return signals
