"""Gold news-candle playbook around real USD events."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.schemas import OHLCV, utcnow
from app.services.economic_calendar import EconomicEvent, upcoming_events
from app.services.trading_bot.candles import load_gold_candles
from app.services.trading_bot.multi_strategy_agent import atr, targets
from app.services.trading_bot.store import signal_payload

GOLD = "XAU_USD"

NEWS_STRATEGIES = {
    "pre_news_gold": {
        "name": "ذهب قبل الخبر",
        "timing": "قبل الخبر بـ 10 دقائق",
        "description": "أوامر معلقة حول السعر الحالي",
    },
    "news_momentum_gold": {
        "name": "زخم شمعة خبر الذهب",
        "timing": "أول 1-3 دقائق بعد الخبر",
        "description": "الدخول مع اتجاه الشمعة الأولى",
    },
    "news_retracement_gold": {
        "name": "ارتداد ذهب الخبر",
        "timing": "5-10 دقائق بعد الخبر",
        "description": "انتظار ارتداد 38-50% فيبوناتشي",
    },
    "news_fade_gold": {
        "name": "عكس خبر الذهب",
        "timing": "10-20 دقيقة بعد الخبر",
        "description": "عكس الحركة عند المبالغة",
    },
}


def identify_news_candle(candles: list[OHLCV], event_time) -> OHLCV | None:
    if not candles:
        return None
    target = event_time.timestamp() * 1000 if hasattr(event_time, "timestamp") else float(event_time)
    return min(candles, key=lambda c: abs(c.timestamp - target))


def analyze_gold_news_candle(candles: list[OHLCV], event_time) -> dict[str, Any]:
    candle = identify_news_candle(candles, event_time)
    if candle is None:
        return {"ok": False, "decision": "wait", "reason": "no candle"}
    rng = max(candle.high - candle.low, 1e-9)
    body = abs(candle.close - candle.open)
    upper = candle.high - max(candle.close, candle.open)
    lower = min(candle.close, candle.open) - candle.low
    vols = [c.volume for c in candles[-20:] if c.volume]
    avg_vol = sum(vols) / len(vols) if vols else 0.0
    body_ratio = body / rng
    upper_ratio = upper / rng
    lower_ratio = lower / rng
    vol_ratio = (candle.volume / avg_vol) if avg_vol else 1.0
    direction = "buy" if candle.close >= candle.open else "sell"
    decision = "wait"
    if body_ratio <= 0.18:
        decision = "wait"
    elif upper_ratio >= 0.6:
        decision = "sell"
    elif lower_ratio >= 0.6:
        decision = "buy"
    elif body_ratio >= 0.7 and vol_ratio >= 1.8:
        decision = direction
    elif body_ratio >= 0.7:
        decision = direction
    return {
        "ok": True,
        "decision": decision,
        "direction": direction,
        "bodyRatio": round(body_ratio, 3),
        "upperWickRatio": round(upper_ratio, 3),
        "lowerWickRatio": round(lower_ratio, 3),
        "volumeRatio": round(vol_ratio, 3),
        "candle": candle.to_kline(),
    }


def pick_news_strategy(minutes_from_event: float, analysis: dict[str, Any]) -> str | None:
    if analysis.get("decision") == "wait" and not (-12 <= minutes_from_event <= -1):
        return None
    if -12 <= minutes_from_event <= -1:
        return "pre_news_gold"
    if 0 <= minutes_from_event <= 3:
        return "news_momentum_gold"
    if 5 <= minutes_from_event <= 10:
        return "news_retracement_gold"
    if 10 < minutes_from_event <= 20:
        return "news_fade_gold"
    return None


class NewsCandleAgent:
    def __init__(self, candle_source=None, events_source=None):
        self.candle_source = candle_source
        self.events_source = events_source

    async def _m1(self, count: int = 40) -> list[OHLCV]:
        if self.candle_source is not None:
            return await self.candle_source(GOLD, "M1", count)
        return await load_gold_candles("M1", count)

    async def _events(self) -> list[EconomicEvent]:
        if self.events_source is not None:
            return await self.events_source()
        payload = await upcoming_events(hours_ahead=6, min_impact="high")
        out = []
        for item in payload.get("events") or []:
            try:
                out.append(EconomicEvent.model_validate(item))
            except Exception:
                continue
        return out

    async def monitor_events(self) -> list[dict[str, Any]]:
        events = await self._events()
        if not events:
            return []
        candles = await self._m1()
        now = utcnow()
        signals: list[dict[str, Any]] = []
        for event in events:
            minutes = (now - event.timestamp).total_seconds() / 60.0
            analysis = analyze_gold_news_candle(candles, event.timestamp)
            strategy = pick_news_strategy(minutes, analysis)
            if not strategy:
                continue
            side = analysis.get("decision") if analysis.get("decision") in {"buy", "sell"} else analysis.get("direction")
            if strategy == "news_fade_gold" and side in {"buy", "sell"}:
                side = "sell" if side == "buy" else "buy"
            if side not in {"buy", "sell"}:
                continue
            last = candles[-1]
            pad = atr(candles) * (0.55 if strategy == "pre_news_gold" else 0.9)
            stop = last.close - pad if side == "buy" else last.close + pad
            tp1, tp2, rr = targets(last.close, stop, side)
            signals.append(
                signal_payload(
                    agent_type="news_candle",
                    strategy_id=strategy,
                    timeframe="M1",
                    signal_type=side,
                    entry=round(last.close, 3),
                    stop=round(stop, 3),
                    tp1=tp1,
                    tp2=tp2,
                    confidence=0.72 if event.impact in {"high", "critical"} else 0.6,
                    risk_reward=rr,
                    economic_event_id=event.id,
                    extra={"eventTitle": event.title, "analysis": analysis, "goldImpact": event.gold_impact},
                )
            )
        return signals
