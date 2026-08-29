from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import (
    KlineOverlay,
    OverlayPoint,
    OverlayStyles,
    Sentiment,
    TakeProfitLevel,
    TradeAction,
    TradeRecommendation,
    TradeSetup,
    OrderType,
    OHLCV,
)
from app.services.simulator import INSTRUMENT_SPECS


@dataclass
class Swing:
    index: int
    timestamp: int
    price: float
    kind: str  # high | low


@dataclass
class FVG:
    start_idx: int
    end_idx: int
    low: float
    high: float
    direction: str  # bullish | bearish
    timestamp_start: int
    timestamp_end: int


@dataclass
class OrderBlock:
    index: int
    timestamp: int
    low: float
    high: float
    direction: str


@dataclass
class StructureReport:
    bias: str
    last_bos: str | None
    swings: list[Swing]
    fvgs: list[FVG]
    order_blocks: list[OrderBlock]
    asian_high: float
    asian_low: float
    liquidity_sweep: str | None
    fib_swing: tuple[Swing, Swing] | None
    confluence: list[str] = field(default_factory=list)


def _fractal_swings(candles: list[OHLCV], left: int = 3) -> list[Swing]:
    swings: list[Swing] = []
    n = len(candles)
    for i in range(left, n - left):
        highs = [candles[j].high for j in range(i - left, i + left + 1)]
        lows = [candles[j].low for j in range(i - left, i + left + 1)]
        if candles[i].high == max(highs):
            swings.append(Swing(i, candles[i].timestamp, candles[i].high, "high"))
        if candles[i].low == min(lows):
            swings.append(Swing(i, candles[i].timestamp, candles[i].low, "low"))
    return swings


def _detect_fvgs(candles: list[OHLCV]) -> list[FVG]:
    fvgs: list[FVG] = []
    for i in range(2, len(candles)):
        a, c = candles[i - 2], candles[i]
        if a.high < c.low:
            fvgs.append(
                FVG(
                    i - 2,
                    i,
                    a.high,
                    c.low,
                    "bullish",
                    a.timestamp,
                    c.timestamp,
                )
            )
        elif a.low > c.high:
            fvgs.append(
                FVG(
                    i - 2,
                    i,
                    c.high,
                    a.low,
                    "bearish",
                    a.timestamp,
                    c.timestamp,
                )
            )
    return fvgs


def _detect_order_blocks(candles: list[OHLCV], swings: list[Swing]) -> list[OrderBlock]:
    blocks: list[OrderBlock] = []
    for swing in swings[-8:]:
        i = swing.index
        if i < 2:
            continue
        candle = candles[i - 1]
        if swing.kind == "high":
            # bearish OB = last bullish candle before dump
            for j in range(i - 1, max(0, i - 6), -1):
                if candles[j].close > candles[j].open:
                    c = candles[j]
                    blocks.append(OrderBlock(j, c.timestamp, c.low, c.high, "bearish"))
                    break
        else:
            for j in range(i - 1, max(0, i - 6), -1):
                if candles[j].close < candles[j].open:
                    c = candles[j]
                    blocks.append(OrderBlock(j, c.timestamp, c.low, c.high, "bullish"))
                    break
    return blocks[-6:]


def _session_range(candles: list[OHLCV], start_h: int, end_h: int) -> tuple[float, float]:
    subset = [c for c in candles[-96:] if start_h <= c.time.hour < end_h]
    if not subset:
        subset = candles[-16:]
    return max(c.high for c in subset), min(c.low for c in subset)


def analyze_structure(candles: list[OHLCV]) -> StructureReport:
    if len(candles) < 20:
        last = candles[-1]
        return StructureReport(
            bias="NEUTRAL",
            last_bos=None,
            swings=[],
            fvgs=[],
            order_blocks=[],
            asian_high=last.high,
            asian_low=last.low,
            liquidity_sweep=None,
            fib_swing=None,
            confluence=["Insufficient history"],
        )

    swings = _fractal_swings(candles)
    fvgs = _detect_fvgs(candles)
    obs = _detect_order_blocks(candles, swings)
    asian_high, asian_low = _session_range(candles, 0, 7)

    last_highs = [s for s in swings if s.kind == "high"]
    last_lows = [s for s in swings if s.kind == "low"]
    close = candles[-1].close
    last_bos = None
    bias = "NEUTRAL"
    if last_highs and close > last_highs[-1].price:
        last_bos = "BULLISH_BOS"
        bias = "BULLISH"
    elif last_lows and close < last_lows[-1].price:
        last_bos = "BEARISH_BOS"
        bias = "BEARISH"
    elif last_highs and last_lows:
        # trend by HH/HL vs LH/LL
        if len(last_highs) >= 2 and last_highs[-1].price > last_highs[-2].price:
            bias = "BULLISH"
        elif len(last_lows) >= 2 and last_lows[-1].price < last_lows[-2].price:
            bias = "BEARISH"

    sweep = None
    wick = candles[-1]
    if wick.low < asian_low and wick.close > asian_low:
        sweep = "BUY_SIDE_RECLAIM_ASIAN_LOW"
        bias = "BULLISH"
    elif wick.high > asian_high and wick.close < asian_high:
        sweep = "SELL_SIDE_RECLAIM_ASIAN_HIGH"
        bias = "BEARISH"

    fib_swing = None
    if last_highs and last_lows:
        a, b = last_lows[-1], last_highs[-1]
        if a.timestamp < b.timestamp:
            fib_swing = (a, b)
        else:
            fib_swing = (b, a)

    confluence: list[str] = []
    if last_bos:
        confluence.append(f"Market structure shift: {last_bos.replace('_', ' ')}")
    if sweep:
        confluence.append(f"Liquidity sweep: {sweep.replace('_', ' ').title()}")
    fresh_fvg = [f for f in fvgs[-6:] if f.direction == ("bullish" if bias == "BULLISH" else "bearish")]
    if fresh_fvg:
        confluence.append(f"{fresh_fvg[-1].direction.title()} FVG still unfilled")
    if obs:
        confluence.append(f"{obs[-1].direction.title()} order block mapped")
    if not confluence:
        confluence.append("Range equilibrium — waiting for displacement")

    return StructureReport(
        bias=bias,
        last_bos=last_bos,
        swings=swings[-16:],
        fvgs=fvgs[-10:],
        order_blocks=obs,
        asian_high=asian_high,
        asian_low=asian_low,
        liquidity_sweep=sweep,
        fib_swing=fib_swing,
        confluence=confluence,
    )


def _rr(entry: float, sl: float, tp: float) -> float:
    risk = abs(entry - sl)
    if risk == 0:
        return 0.0
    return round(abs(tp - entry) / risk, 2)


def build_recommendation(
    symbol: str,
    timeframe: str,
    candles: list[OHLCV],
    htf_bias: str | None = None,
    model: str | None = None,
    vision_notes: str | None = None,
) -> TradeRecommendation:
    report = analyze_structure(candles)
    bias = htf_bias or report.bias
    if bias == "NEUTRAL":
        bias = "BULLISH" if candles[-1].close >= candles[-1].open else "BEARISH"

    spec = INSTRUMENT_SPECS.get(symbol, INSTRUMENT_SPECS["XAU_USD"])
    last = candles[-1]
    pip = spec["pip"]
    atr = sum(c.high - c.low for c in candles[-14:]) / 14
    atr = max(atr, pip * 8)

    aligned_fvg = [f for f in report.fvgs if f.direction == ("bullish" if bias == "BULLISH" else "bearish")]
    aligned_ob = [b for b in report.order_blocks if b.direction == ("bullish" if bias == "BULLISH" else "bearish")]

    if bias == "BULLISH":
        if aligned_fvg:
            zone = aligned_fvg[-1]
            entry = (zone.low + zone.high) / 2
        elif aligned_ob:
            zone_ob = aligned_ob[-1]
            entry = (zone_ob.low + zone_ob.high) / 2
        else:
            entry = last.close - atr * 0.35
        sl = min(c.low for c in candles[-8:]) - atr * 0.25
        if sl >= entry:
            sl = entry - atr * 0.8
        tp1 = entry + (entry - sl) * 1.6
        tp2 = entry + (entry - sl) * 3.0
        action = TradeAction.BUY
        order = OrderType.LIMIT
    else:
        if aligned_fvg:
            zone = aligned_fvg[-1]
            entry = (zone.low + zone.high) / 2
        elif aligned_ob:
            zone_ob = aligned_ob[-1]
            entry = (zone_ob.low + zone_ob.high) / 2
        else:
            entry = last.close + atr * 0.35
        sl = max(c.high for c in candles[-8:]) + atr * 0.25
        if sl <= entry:
            sl = entry + atr * 0.8
        tp1 = entry - (sl - entry) * 1.6
        tp2 = entry - (sl - entry) * 3.0
        action = TradeAction.SELL
        order = OrderType.LIMIT

    rr = _rr(entry, sl, tp2)
    overlays = _build_overlays(candles, report, entry, sl, tp1, tp2, action, timeframe)
    focus = aligned_fvg[-1].timestamp_start if aligned_fvg else last.timestamp

    rationale_bits = [
        f"{symbol.replace('_', '/')} {timeframe} {bias.lower()} thesis.",
    ]
    if report.liquidity_sweep:
        rationale_bits.append("Liquidity sweep of the Asian session extreme with displacement back inside the range.")
    if aligned_fvg:
        rationale_bits.append("Price is mitigating a fresh Fair Value Gap — entry anchored at zone equilibrium.")
    if report.last_bos:
        rationale_bits.append("Break of structure confirms the directional intent.")
    if htf_bias:
        rationale_bits.append(f"Higher-timeframe bias is {htf_bias}.")
    if vision_notes:
        rationale_bits.append(vision_notes.strip())
    rationale = " ".join(rationale_bits)

    return TradeRecommendation(
        symbol=symbol,
        timeframe=timeframe,
        sentiment=Sentiment(bias if bias in {"BULLISH", "BEARISH"} else "NEUTRAL"),
        tradeSetup=TradeSetup(
            action=action,
            orderType=order,
            entryPrice=round(entry, spec["decimals"]),
            stopLoss=round(sl, spec["decimals"]),
            takeProfitLevels=[
                TakeProfitLevel(level=1, price=round(tp1, spec["decimals"]), ratio="1:1.6"),
                TakeProfitLevel(level=2, price=round(tp2, spec["decimals"]), ratio="1:3.0"),
            ],
            riskRewardRatio=rr,
        ),
        rationale=rationale,
        confluence=report.confluence,
        klineOverlays=overlays,
        model=model,
        visionNotes=vision_notes,
        focusTimestamp=focus,
    )


def _pt(ts: int, value: float) -> OverlayPoint:
    return OverlayPoint(timestamp=int(ts), value=float(value))


def _build_overlays(
    candles: list[OHLCV],
    report: StructureReport,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    action: TradeAction,
    timeframe: str,
) -> list[KlineOverlay]:
    overlays: list[KlineOverlay] = []
    last = candles[-1]
    t0 = candles[max(0, len(candles) - 80)].timestamp
    t1 = last.timestamp

    bull = action == TradeAction.BUY
    zone_fill = "rgba(34, 197, 94, 0.18)" if bull else "rgba(239, 68, 68, 0.18)"
    zone_border = "#22c55e" if bull else "#ef4444"

    fvgs = [f for f in report.fvgs if f.direction == ("bullish" if bull else "bearish")]
    if fvgs:
        f = fvgs[-1]
        overlays.append(
            KlineOverlay(
                name="rect",
                groupId="fvg_zone",
                points=[_pt(f.timestamp_start, f.low), _pt(min(f.timestamp_end + 4 * (last.timestamp - candles[-2].timestamp), t1), f.high)],
                styles=OverlayStyles(fillColor=zone_fill, borderColor=zone_border),
                annotationText=f"{timeframe} {'Bullish' if bull else 'Bearish'} FVG",
            )
        )

    if report.order_blocks:
        ob = report.order_blocks[-1]
        overlays.append(
            KlineOverlay(
                name="rect",
                groupId="order_block",
                points=[_pt(ob.timestamp, ob.low), _pt(t1, ob.high)],
                styles=OverlayStyles(
                    fillColor="rgba(59, 130, 246, 0.16)",
                    borderColor="#3b82f6",
                ),
                annotationText="Order Block",
            )
        )

    if report.fib_swing:
        a, b = report.fib_swing
        overlays.append(
            KlineOverlay(
                name="fibonacci",
                groupId="fib_retracement",
                points=[_pt(a.timestamp, a.price), _pt(b.timestamp, b.price)],
                styles=OverlayStyles(lineColor="#eab308", lineWidth=1),
            )
        )

    if len(report.swings) >= 2:
        s0, s1 = report.swings[-2], report.swings[-1]
        overlays.append(
            KlineOverlay(
                name="trendLine",
                groupId="liquidity_trendline",
                points=[_pt(s0.timestamp, s0.price), _pt(s1.timestamp, s1.price)],
                styles=OverlayStyles(lineColor="#eab308", lineWidth=2),
            )
        )

    overlays.append(
        KlineOverlay(
            name="trendLine",
            groupId="asian_low",
            points=[_pt(t0, report.asian_low), _pt(t1, report.asian_low)],
            styles=OverlayStyles(lineColor="#22d3ee", lineWidth=1),
            annotationText="Asian Session Low",
        )
    )
    overlays.append(
        KlineOverlay(
            name="trendLine",
            groupId="asian_high",
            points=[_pt(t0, report.asian_high), _pt(t1, report.asian_high)],
            styles=OverlayStyles(lineColor="#a78bfa", lineWidth=1),
            annotationText="Asian Session High",
        )
    )

    levels = [
        ("entry", entry, "#f8fafc", "Entry"),
        ("sl", sl, "#ef4444", "SL"),
        ("tp1", tp1, "#22c55e", "TP1"),
        ("tp2", tp2, "#4ade80", "TP2"),
    ]
    for gid, price, color, label in levels:
        overlays.append(
            KlineOverlay(
                name="priceLine",
                groupId=gid,
                points=[_pt(last.timestamp, price)],
                styles=OverlayStyles(lineColor=color, color=color, lineWidth=1),
                annotationText=label,
                extendData=label,
            )
        )

    if report.liquidity_sweep:
        overlays.append(
            KlineOverlay(
                name="textAnnotation",
                groupId="note_sweep",
                points=[_pt(last.timestamp, last.low if bull else last.high)],
                styles=OverlayStyles(color="#fbbf24", textColor="#0b1220", backgroundColor="#fbbf24"),
                annotationText="Liquidity Grab",
                extendData="Liquidity Grab",
            )
        )
    if fvgs:
        overlays.append(
            KlineOverlay(
                name="textAnnotation",
                groupId="note_fvg",
                points=[_pt(fvgs[-1].timestamp_end, (fvgs[-1].low + fvgs[-1].high) / 2)],
                extendData="FVG Entry Zone",
                annotationText="FVG Entry Zone",
                styles=OverlayStyles(color="#22c55e" if bull else "#ef4444"),
            )
        )
    return overlays


def calculate_ict_levels(candles: list[OHLCV]) -> dict:
    """Rich ICT map used by TechnicalAgent (FVGs, OBs, session liquidity, swings)."""
    report = analyze_structure(candles)
    summary = structure_summary(report)
    summary["orderBlockZones"] = [
        {
            "direction": block.direction,
            "low": block.low,
            "high": block.high,
            "timestamp": block.timestamp,
        }
        for block in report.order_blocks[-6:]
    ]
    if report.fib_swing:
        left, right = report.fib_swing
        summary["fibonacciSwing"] = {
            "from": {"timestamp": left.timestamp, "price": left.price, "kind": left.kind},
            "to": {"timestamp": right.timestamp, "price": right.price, "kind": right.kind},
        }
    return summary


def structure_summary(report: StructureReport) -> dict:
    return {
        "bias": report.bias,
        "lastBos": report.last_bos,
        "fvgCount": len(report.fvgs),
        "orderBlocks": len(report.order_blocks),
        "liquiditySweep": report.liquidity_sweep,
        "asianHigh": report.asian_high,
        "asianLow": report.asian_low,
        "confluence": report.confluence,
        "swings": [
            {"index": s.index, "timestamp": s.timestamp, "price": s.price, "kind": s.kind}
            for s in report.swings[-8:]
        ],
        "fvgs": [
            {
                "direction": f.direction,
                "low": f.low,
                "high": f.high,
                "timestampStart": f.timestamp_start,
                "timestampEnd": f.timestamp_end,
            }
            for f in report.fvgs[-5:]
        ],
    }
