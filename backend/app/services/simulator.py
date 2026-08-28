from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from app.schemas import LivePrice, OHLCV

INSTRUMENT_SPECS: dict[str, dict] = {
    "XAU_USD": {"price": 2654.20, "vol": 0.0018, "decimals": 2, "pip": 0.1, "name": "Gold", "display": "XAU/USD"},
    "EUR_USD": {"price": 1.08540, "vol": 0.00055, "decimals": 5, "pip": 0.0001, "name": "Euro", "display": "EUR/USD"},
    "GBP_USD": {"price": 1.27320, "vol": 0.00062, "decimals": 5, "pip": 0.0001, "name": "Sterling", "display": "GBP/USD"},
    "GBP_JPY": {"price": 193.450, "vol": 0.00085, "decimals": 3, "pip": 0.01, "name": "Cable Yen", "display": "GBP/JPY"},
    "USD_JPY": {"price": 151.820, "vol": 0.00058, "decimals": 3, "pip": 0.01, "name": "Dollar Yen", "display": "USD/JPY"},
    "AUD_USD": {"price": 0.66210, "vol": 0.00070, "decimals": 5, "pip": 0.0001, "name": "Aussie", "display": "AUD/USD"},
    "USD_CAD": {"price": 1.35880, "vol": 0.00052, "decimals": 5, "pip": 0.0001, "name": "Loonie", "display": "USD/CAD"},
    "EUR_JPY": {"price": 164.720, "vol": 0.00072, "decimals": 3, "pip": 0.01, "name": "Euro Yen", "display": "EUR/JPY"},
    "NZD_USD": {"price": 0.60140, "vol": 0.00075, "decimals": 5, "pip": 0.0001, "name": "Kiwi", "display": "NZD/USD"},
    "USD_CHF": {"price": 0.88420, "vol": 0.00048, "decimals": 5, "pip": 0.0001, "name": "Swissy", "display": "USD/CHF"},
}

GRANULARITY_SECONDS: dict[str, int] = {
    "S5": 5,
    "S15": 15,
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D": 86400,
    "W": 604800,
}

TF_TO_GRANULARITY = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "1H": "H1",
    "4h": "H4",
    "4H": "H4",
    "1d": "D",
    "1D": "D",
    "D": "D",
}


def normalize_granularity(tf: str) -> str:
    key = tf.strip()
    if key in GRANULARITY_SECONDS:
        return key
    return TF_TO_GRANULARITY.get(key, TF_TO_GRANULARITY.get(key.lower(), "M15"))


def _seed_for(instrument: str, granularity: str) -> int:
    return abs(hash(f"{instrument}:{granularity}:foxagent")) % (2**31)


def _session_multiplier(dt: datetime) -> float:
    hour = dt.hour
    if 0 <= hour < 7:
        return 0.55
    if 7 <= hour < 12:
        return 1.15
    if 12 <= hour < 16:
        return 1.35
    if 16 <= hour < 21:
        return 1.05
    return 0.7


def generate_candles(
    instrument: str,
    granularity: str,
    count: int,
    end: datetime | None = None,
) -> list[OHLCV]:
    spec = INSTRUMENT_SPECS.get(instrument, INSTRUMENT_SPECS["XAU_USD"])
    seconds = GRANULARITY_SECONDS.get(granularity, 900)
    end = end or datetime.now(timezone.utc)
    end = end.replace(microsecond=0)
    epoch = int(end.timestamp())
    epoch -= epoch % seconds
    start_epoch = epoch - seconds * (count - 1)

    rng = random.Random(_seed_for(instrument, granularity))
    price = spec["price"]
    vol = spec["vol"]
    candles: list[OHLCV] = []
    trend = rng.choice([-1, 1]) * vol * 0.15

    for i in range(count):
        ts = start_epoch + i * seconds
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        sess = _session_multiplier(dt)
        if i and i % max(24, count // 8) == 0:
            trend *= -0.85
            trend += rng.uniform(-vol, vol) * 0.2
        shock = rng.gauss(trend, vol * sess)
        sweep = rng.random() < 0.04
        open_px = price
        close_px = max(1e-8, open_px * math.exp(shock))
        high_ext = abs(rng.gauss(0, vol * sess)) * open_px
        low_ext = abs(rng.gauss(0, vol * sess)) * open_px
        high = max(open_px, close_px) + high_ext
        low = min(open_px, close_px) - low_ext
        if sweep:
            if rng.random() < 0.5:
                low -= (high - low) * rng.uniform(0.6, 1.4)
            else:
                high += (high - low) * rng.uniform(0.6, 1.4)
        if i % 41 == 17:
            impulse = (1 if close_px >= open_px else -1) * open_px * vol * sess * 4.2
            close_px = open_px + impulse
            high = max(high, close_px)
            low = min(low, open_px)
        volume = abs(rng.gauss(1800, 420)) * sess
        candles.append(
            OHLCV(
                time=dt,
                timestamp=ts * 1000,
                open=round(open_px, spec["decimals"]),
                high=round(high, spec["decimals"]),
                low=round(low, spec["decimals"]),
                close=round(close_px, spec["decimals"]),
                volume=round(volume, 1),
                complete=i < count - 1,
            )
        )
        price = close_px

    return candles


class TickSimulator:
    def __init__(self) -> None:
        self._mids: dict[str, float] = {k: v["price"] for k, v in INSTRUMENT_SPECS.items()}
        self._rng = random.Random(42)

    def tick(self, instrument: str) -> LivePrice:
        spec = INSTRUMENT_SPECS.get(instrument, INSTRUMENT_SPECS["XAU_USD"])
        mid = self._mids.get(instrument, spec["price"])
        shock = self._rng.gauss(0, spec["vol"] * 0.08)
        mid = max(1e-8, mid * math.exp(shock))
        self._mids[instrument] = mid
        spread = spec["pip"] * (1.2 if instrument.startswith("XAU") else 0.8)
        bid = mid - spread / 2
        ask = mid + spread / 2
        now = datetime.now(timezone.utc)
        return LivePrice(
            instrument=instrument,
            bid=round(bid, spec["decimals"]),
            ask=round(ask, spec["decimals"]),
            mid=round(mid, spec["decimals"]),
            time=now,
            spread=round(spread, spec["decimals"] + 1),
            source="simulator",
        )

    def apply_close(self, instrument: str, close: float) -> None:
        self._mids[instrument] = close


simulator = TickSimulator()
