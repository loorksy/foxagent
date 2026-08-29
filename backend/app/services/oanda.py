from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from app.config import get_settings
from app.schemas import LivePrice, OHLCV
from app.services.simulator import generate_candles, normalize_granularity, simulator

logger = logging.getLogger(__name__)


def _parse_oanda_time(value: str) -> datetime:
    raw = value.replace("Z", "+00:00")
    if "." in raw:
        head, rest = raw.split(".", 1)
        frac, tz = rest.split("+", 1) if "+" in rest else (rest, "00:00")
        frac = (frac + "000000")[:6]
        raw = f"{head}.{frac}+{tz}"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _candle_from_oanda(item: dict[str, Any]) -> OHLCV | None:
    mid = item.get("mid") or item.get("bid") or item.get("ask")
    if not mid:
        return None
    dt = _parse_oanda_time(item["time"])
    return OHLCV(
        time=dt,
        timestamp=int(dt.timestamp() * 1000),
        open=float(mid["o"]),
        high=float(mid["h"]),
        low=float(mid["l"]),
        close=float(mid["c"]),
        volume=float(item.get("volume", 0)),
        complete=bool(item.get("complete", True)),
    )


class OandaClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        settings = get_settings()
        return {
            "Authorization": f"Bearer {settings.oanda_api_token}",
            "Accept-Datetime-Format": "RFC3339",
            "Content-Type": "application/json",
        }

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def fetch_remote_candles(
        self,
        instrument: str,
        granularity: str,
        count: int | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        include_first: bool = False,
    ) -> list[OHLCV]:
        """One OANDA/simulator page. Max 5000 candles (OANDA v20 limit)."""
        from app.services.gold_sync import OandaRateLimitError

        gran = normalize_granularity(granularity)
        if gran == "D1":
            gran = "D"
        settings = get_settings()
        page = min(count or 500, 5000)
        if not settings.oanda_configured:
            end = to_time
            candles = generate_candles(instrument, gran, page, end=end)
            if from_time:
                candles = [c for c in candles if c.time > from_time or (include_first and c.time >= from_time)]
            if to_time and not from_time:
                candles = [c for c in candles if c.time < to_time]
            if candles:
                simulator.apply_close(instrument, candles[-1].close)
            return candles

        url = f"{settings.oanda_rest_base}/v3/instruments/{instrument}/candles"
        params: dict[str, str] = {"granularity": gran, "price": "M"}
        if from_time is not None:
            params["from"] = from_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            params["includeFirst"] = "true" if include_first else "false"
        if to_time is not None:
            params["to"] = to_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not (from_time is not None and to_time is not None):
            params["count"] = str(page)
        client = await self._client()
        resp = await client.get(url, headers=self._headers(), params=params)
        if resp.status_code == 429:
            raise OandaRateLimitError(resp.text[:200])
        resp.raise_for_status()
        data = resp.json()
        candles: list[OHLCV] = []
        for item in data.get("candles", []):
            parsed = _candle_from_oanda(item)
            if parsed:
                candles.append(parsed)
        if candles:
            simulator.apply_close(instrument, candles[-1].close)
        return candles

    async def get_candles(
        self,
        instrument: str,
        granularity: str,
        count: int = 300,
    ) -> list[OHLCV]:
        from app.services.gold_sync import read_gold_candles
        from app.services.gold_warehouse import uses_warehouse

        gran = normalize_granularity(granularity)
        settings = get_settings()
        source = "oanda" if settings.oanda_configured else "simulator"
        if uses_warehouse(instrument, gran):
            try:
                return await read_gold_candles(
                    gran,
                    count,
                    self.fetch_remote_candles,
                    source=source,
                )
            except Exception as exc:
                logger.warning("Gold warehouse read failed (%s), falling through to live: %s", gran, exc)

        try:
            candles = await self.fetch_remote_candles(instrument, gran, count=count)
            if candles:
                return candles
        except Exception as exc:
            logger.warning("OANDA candles failed (%s), using simulator: %s", instrument, exc)
        candles = generate_candles(instrument, gran, count)
        if candles:
            simulator.apply_close(instrument, candles[-1].close)
        return candles

    async def get_live_price(self, instrument: str) -> LivePrice:
        settings = get_settings()
        if not settings.oanda_configured:
            return simulator.tick(instrument)
        url = f"{settings.oanda_rest_base}/v3/accounts/{settings.oanda_account_id}/pricing"
        try:
            client = await self._client()
            resp = await client.get(
                url,
                headers=self._headers(),
                params={"instruments": instrument},
            )
            resp.raise_for_status()
            prices = resp.json().get("prices", [])
            if not prices:
                return simulator.tick(instrument)
            p = prices[0]
            bids = p.get("bids") or [{"price": p.get("closeoutBid")}]
            asks = p.get("asks") or [{"price": p.get("closeoutAsk")}]
            bid = float(bids[0]["price"])
            ask = float(asks[0]["price"])
            mid = (bid + ask) / 2
            t = _parse_oanda_time(p.get("time") or datetime.now(timezone.utc).isoformat())
            return LivePrice(
                instrument=instrument,
                bid=bid,
                ask=ask,
                mid=mid,
                time=t,
                spread=ask - bid,
                source="oanda",
            )
        except Exception as exc:
            logger.warning("OANDA pricing failed, using simulator: %s", exc)
            return simulator.tick(instrument)

    async def stream_prices(self, instruments: list[str]) -> AsyncIterator[LivePrice]:
        settings = get_settings()
        if not settings.oanda_configured:
            return
            yield  # pragma: no cover
        url = f"{settings.oanda_stream_base}/v3/accounts/{settings.oanda_account_id}/pricing/stream"
        try:
            client = await self._client()
            async with client.stream(
                "GET",
                url,
                headers=self._headers(),
                params={"instruments": ",".join(instruments)},
                timeout=None,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    import json

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("type") != "PRICE":
                        continue
                    bids = payload.get("bids") or []
                    asks = payload.get("asks") or []
                    if not bids or not asks:
                        continue
                    bid = float(bids[0]["price"])
                    ask = float(asks[0]["price"])
                    yield LivePrice(
                        instrument=payload["instrument"],
                        bid=bid,
                        ask=ask,
                        mid=(bid + ask) / 2,
                        time=_parse_oanda_time(payload["time"]),
                        spread=ask - bid,
                        source="oanda",
                    )
        except Exception as exc:
            logger.warning("OANDA stream ended: %s", exc)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


oanda = OandaClient()
