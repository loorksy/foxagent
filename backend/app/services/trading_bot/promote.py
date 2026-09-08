"""Promote a high-confidence bot signal into a TradeRecommendation (risk-gated)."""

from __future__ import annotations

from typing import Any

from app.schemas import (
    KlineOverlay,
    OverlayPoint,
    OverlayStyles,
    Sentiment,
    TakeProfitLevel,
    TradeAction,
    TradeRecommendation,
    TradeSetup,
)
from app.services.mcp_tools import persist_recommendation
from app.services.trading_bot.store import get_signal, update_signal


def signal_to_recommendation(signal: dict[str, Any]) -> TradeRecommendation:
    side = str(signal.get("signalType") or "buy").lower()
    action = TradeAction.BUY if side == "buy" else TradeAction.SELL
    entry = float(signal.get("entryPrice") or 0)
    sl = float(signal.get("stopLoss") or 0)
    tp1 = float(signal.get("takeProfit1") or 0)
    tp2 = float(signal.get("takeProfit2") or 0)
    ts = int(signal.get("focusTimestamp") or 0)
    extra = signal.get("metadata") or {}
    overlays = [
        KlineOverlay(
            name="priceLine",
            groupId=signal["id"],
            points=[OverlayPoint(timestamp=ts or 0, value=entry)],
            styles=OverlayStyles(lineColor="#22c55e" if action == TradeAction.BUY else "#ef4444"),
            annotationText="Entry",
        )
    ]
    return TradeRecommendation(
        symbol=signal.get("instrument") or "XAU_USD",
        timeframe=signal.get("timeframe") or "M15",
        sentiment=Sentiment.BULLISH if action == TradeAction.BUY else Sentiment.BEARISH,
        tradeSetup=TradeSetup(
            action=action,
            entryPrice=entry,
            stopLoss=sl,
            takeProfitLevels=[
                TakeProfitLevel(level=1, price=tp1, ratio="1:1.5"),
                TakeProfitLevel(level=2, price=tp2, ratio="1:3.0"),
            ],
            riskRewardRatio=float(signal.get("riskReward") or 3.0),
        ),
        rationale=str(extra.get("rationale") or f"Bot {signal.get('strategyId')} on gold"),
        confluence=list(extra.get("confluence") or [str(signal.get("strategyId"))]),
        klineOverlays=overlays,
        model="foxagent-gold-bot",
        focusTimestamp=ts or None,
    )


async def promote_signal(signal_id: str) -> dict[str, Any]:
    signal = await get_signal(signal_id)
    if signal is None:
        return {"ok": False, "detail": "Signal not found"}
    rec = signal_to_recommendation(signal)
    result = await persist_recommendation(rec)
    if result.get("ok"):
        await update_signal(signal_id, {"recommendationId": rec.id, "status": "active"})
    return result
