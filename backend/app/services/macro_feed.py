from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

import httpx

from app.services.analysis import analyze_structure
from app.services.oanda import oanda


def current_session(now: datetime | None = None) -> dict[str, Any]:
    hour = (now or datetime.now(timezone.utc)).hour
    if 0 <= hour < 7:
        name = "asian"
    elif 7 <= hour < 12:
        name = "london"
    elif 12 <= hour < 16:
        name = "london_ny_overlap"
    elif 16 <= hour < 21:
        name = "ny"
    else:
        name = "late_ny_asia"
    return {"session": name, "utcHour": hour}


async def get_economic_calendar(instrument: str = "XAU_USD") -> dict[str, Any]:
    """Session clock from real UTC time — no invented print events."""
    session = current_session()
    return {
        "instrument": instrument,
        "source": "session-clock",
        "asOf": datetime.now(timezone.utc).isoformat(),
        **session,
        "windows": [
            {"name": "asian", "utc": "00:00-07:00"},
            {"name": "london", "utc": "07:00-16:00"},
            {"name": "ny", "utc": "12:00-21:00"},
        ],
        "note": "No third-party economic calendar is configured. Session windows are deterministic UTC hours.",
    }


async def get_market_sentiment(instrument: str = "XAU_USD") -> dict[str, Any]:
    candles = await oanda.get_candles(instrument, "H1", 120)
    report = analyze_structure(candles)
    px = await oanda.get_live_price(instrument)
    return {
        "instrument": instrument,
        "bias": report.bias,
        "lastBos": report.last_bos,
        "liquiditySweep": report.liquidity_sweep,
        "confluence": report.confluence,
        "mid": px.mid,
        "spread": px.spread,
        "source": px.source,
        "session": current_session(),
    }


async def fetch_financial_news(instrument: str = "XAU_USD") -> dict[str, Any]:
    url = "https://feeds.reuters.com/reuters/businessNews"
    items: list[dict[str, str]] = []
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
        for node in root.findall(".//item")[:8]:
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            if title:
                items.append({"title": title, "link": link})
    except Exception as exc:
        return {"ok": False, "instrument": instrument, "items": [], "detail": str(exc)[:200]}
    return {"ok": True, "instrument": instrument, "source": url, "items": items}
