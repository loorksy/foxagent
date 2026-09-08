"""Gold candle loader: warehouse first, then OANDA, then the deterministic simulator."""

from __future__ import annotations

from app.schemas import OHLCV
from app.services.oanda import oanda
from app.services.simulator import generate_candles, normalize_granularity

GOLD = "XAU_USD"


async def load_gold_candles(timeframe: str, count: int = 180) -> list[OHLCV]:
    gran = normalize_granularity(timeframe)
    try:
        from app.services.gold_warehouse import load_latest

        stored = await load_latest(gran, count)
        if stored:
            return stored
    except Exception:
        pass
    try:
        data = await oanda.get_candles(GOLD, gran, count)
        if data:
            return data
    except Exception:
        pass
    return generate_candles(GOLD, gran, count)
