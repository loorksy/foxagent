"""Real USD economic calendar for gold (XAU_USD).

Forex Factory is scraped when network fetch is enabled. Trading Economics is a
paid-API skeleton. Failures return an empty list — never invented prints.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, SessionLocal
from app.schemas import utcnow, new_id

logger = logging.getLogger(__name__)

FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"
GOLD_INSTRUMENT = "XAU_USD"
IMPACT_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
USD_ALIASES = {"usd", "united states", "us", "u.s."}
WATCHLIST = (
    "nfp",
    "non-farm",
    "nonfarm",
    "payroll",
    "cpi",
    "fomc",
    "federal funds",
    "interest rate",
    "gdp",
    "unemployment",
    "jobless",
    "retail sales",
    "pmi",
    "ism",
    "ppi",
    "core pce",
    "powell",
    "fomc minutes",
    "dot plot",
    "average hourly",
    "hourly earnings",
    "claims",
    "core cpi",
    "core pce",
    "ism manufacturing",
    "ism services",
)
USD_STRENGTH_TITLES = (
    "nfp",
    "non-farm",
    "nonfarm",
    "payroll",
    "cpi",
    "ppi",
    "gdp",
    "retail sales",
    "pmi",
    "ism",
    "federal funds",
    "interest rate",
)
USD_WEAKNESS_IF_HIGHER = ("unemployment", "jobless", "claims")

_memory_events: dict[str, dict[str, Any]] = {}
_cache: tuple[float, list["EconomicEvent"], str] | None = None


class EconomicEvent(BaseModel):
    id: str
    title: str
    country: str = "USD"
    timestamp: datetime
    impact: Literal["low", "medium", "high", "critical"]
    forecast: float | None = None
    previous: float | None = None
    actual: float | None = None
    unit: str = ""
    source: str = "forex_factory"
    related_instruments: list[str] = Field(default_factory=lambda: [GOLD_INSTRUMENT])
    description: str | None = None
    gold_impact: Literal["positive", "negative", "neutral"] = "neutral"


class EconomicEventRow(Base):
    __tablename__ = "economic_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(8), default="USD")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    impact: Mapped[str] = mapped_column(String(16))
    forecast: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    gold_impact: Mapped[str] = mapped_column(String(16), default="neutral")
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="forex_factory")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EconomicCalendarProvider(ABC):
    name = "base"

    @abstractmethod
    async def fetch_events(self, start_date: datetime, end_date: datetime) -> list[EconomicEvent]:
        raise NotImplementedError


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def parse_numeric(raw: str | None) -> tuple[float | None, str]:
    if not raw:
        return None, ""
    text = _clean(raw).replace(",", "")
    if text in {"", "-", "—", "n/a", "N/A"}:
        return None, ""
    unit = ""
    if text.endswith("%"):
        unit = "%"
        text = text[:-1]
    elif text.upper().endswith("K"):
        unit = "K"
        text = text[:-1]
    elif text.upper().endswith("B"):
        unit = "B"
        text = text[:-1]
    elif text.upper().endswith("M"):
        unit = "M"
        text = text[:-1]
    try:
        return float(text), unit
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None, unit
        return float(match.group()), unit


def classify_impact(raw: str) -> Literal["low", "medium", "high", "critical"]:
    text = (raw or "").lower()
    if "critical" in text or "red" in text or "high" in text or "impact-red" in text:
        return "high"
    if "orange" in text or "med" in text or "impact-ora" in text:
        return "medium"
    if "yellow" in text or "low" in text or "impact-yel" in text:
        return "low"
    if "gray" in text or "holiday" in text:
        return "low"
    return "medium"


def upgrade_impact(title: str, impact: str) -> str:
    lowered = title.lower()
    if any(key in lowered for key in ("fomc", "non-farm", "nonfarm", "nfp", "cpi", "federal funds")):
        return "critical" if impact in {"high", "critical"} else impact
    return impact


def infer_gold_impact(title: str, actual: float | None, forecast: float | None) -> str:
    if actual is None or forecast is None:
        return "neutral"
    lowered = title.lower()
    stronger_usd = actual > forecast
    if any(key in lowered for key in USD_WEAKNESS_IF_HIGHER):
        stronger_usd = actual < forecast
    elif not any(key in lowered for key in USD_STRENGTH_TITLES):
        return "neutral"
    if actual == forecast:
        return "neutral"
    # Stronger USD typically weighs on gold.
    return "negative" if stronger_usd else "positive"


def is_usd_event(country: str) -> bool:
    return (country or "").strip().lower() in USD_ALIASES


def is_watchlist(title: str) -> bool:
    lowered = title.lower()
    return any(key in lowered for key in WATCHLIST)


def event_id_for(title: str, stamp: datetime, country: str = "USD") -> str:
    raw = f"{country}|{title.strip().lower()}|{stamp.astimezone(timezone.utc).isoformat()}"
    return "ev_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse_ff_time(day: datetime, raw: str, tz_name: str = "America/New_York") -> datetime:
    text = _clean(raw).lower()
    if not text or text in {"all day", "tentative", "all-day"}:
        return day.replace(hour=0, minute=0, second=0, microsecond=0)
    match = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", text)
    if not match:
        return day
    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    local = day.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz)
    return local.astimezone(timezone.utc)


def parse_ff_day(raw: str, fallback: datetime) -> datetime:
    text = _clean(raw)
    if not text:
        return fallback
    for fmt in ("%a %b %d", "%B %d", "%b %d", "%a %b %d %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            year = fallback.year
            return fallback.replace(month=parsed.month, day=parsed.day, year=year, hour=0, minute=0)
        except ValueError:
            continue
    return fallback


def parse_forex_factory_html(html: str, *, week_start: datetime | None = None) -> list[EconomicEvent]:
    """Parse a Forex Factory calendar HTML snapshot. Tested against fixtures."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    rows = soup.select("tr.calendar__row, tr.calendar_row, tr[data-event-id]")
    day = (week_start or utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
    events: list[EconomicEvent] = []
    for row in rows:
        classes = " ".join(row.get("class") or [])
        date_cell = row.select_one(".calendar__date, .date, td.calendar__cell.calendar__date")
        if date_cell and _clean(date_cell.get_text()):
            day = parse_ff_day(date_cell.get_text(), day)
        if "day-breaker" in classes or "calendar__row--new-day" in classes:
            continue
        currency = _clean((row.select_one(".calendar__currency, .calendar__cell.calendar__currency") or row).get_text())
        # Isolated currency cells often contain only USD / EUR.
        cur_el = row.select_one(".calendar__currency")
        if cur_el is not None:
            currency = _clean(cur_el.get_text())
        if not is_usd_event(currency):
            continue
        title_el = row.select_one(".calendar__event, .calendar__event-title, .event")
        title = _clean(title_el.get_text() if title_el else "")
        if not title or not is_watchlist(title):
            continue
        time_el = row.select_one(".calendar__time")
        stamp = parse_ff_time(day, time_el.get_text() if time_el else "")
        impact_el = row.select_one(".calendar__impact, .impact")
        impact_raw = ""
        if impact_el:
            span = impact_el.find("span") or impact_el
            impact_raw = " ".join(filter(None, [span.get("class") and " ".join(span.get("class")), span.get("title"), impact_el.get_text()]))
        impact = upgrade_impact(title, classify_impact(impact_raw))
        actual, unit_a = parse_numeric(row.select_one(".calendar__actual").get_text() if row.select_one(".calendar__actual") else "")
        forecast, unit_f = parse_numeric(row.select_one(".calendar__forecast").get_text() if row.select_one(".calendar__forecast") else "")
        previous, unit_p = parse_numeric(row.select_one(".calendar__previous").get_text() if row.select_one(".calendar__previous") else "")
        unit = unit_a or unit_f or unit_p
        ev_id = row.get("data-event-id") or event_id_for(title, stamp)
        events.append(
            EconomicEvent(
                id=str(ev_id)[:64],
                title=title,
                country="USD",
                timestamp=stamp,
                impact=impact,  # type: ignore[arg-type]
                forecast=forecast,
                previous=previous,
                actual=actual,
                unit=unit,
                source="forex_factory",
                gold_impact=infer_gold_impact(title, actual, forecast),  # type: ignore[arg-type]
                description=f"USD print watched for gold: {title}",
            )
        )
    return events


class ForexFactoryProvider(EconomicCalendarProvider):
    name = "forex_factory"

    def __init__(self, fetch_html=None):
        self._fetch_html = fetch_html

    async def _download(self) -> str:
        if self._fetch_html is not None:
            return await self._fetch_html()
        if os.environ.get("FOXAGENT_CALENDAR_FETCH", "1").strip().lower() in {"0", "false", "off", "no"}:
            raise RuntimeError("Network calendar fetch is disabled in this process")
        import httpx

        headers = {
            "User-Agent": "FoxAgent/1.0 (gold desk calendar; +https://foxagent.lork.cloud)",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(FOREX_FACTORY_URL)
            resp.raise_for_status()
            return resp.text

    async def fetch_events(self, start_date: datetime, end_date: datetime) -> list[EconomicEvent]:
        html = await self._download()
        events = parse_forex_factory_html(html, week_start=start_date)
        return [e for e in events if start_date <= e.timestamp <= end_date]


class TradingEconomicsProvider(EconomicCalendarProvider):
    """Paid API skeleton — requires a key from settings before it can fetch."""

    name = "trading_economics"

    async def fetch_events(self, start_date: datetime, end_date: datetime) -> list[EconomicEvent]:
        logger.info("TradingEconomicsProvider is a skeleton; no paid key is configured")
        return []


def _event_to_row(event: EconomicEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "country": event.country,
        "timestamp": event.timestamp,
        "impact": event.impact,
        "forecast": event.forecast,
        "previous": event.previous,
        "actual": event.actual,
        "gold_impact": event.gold_impact,
        "is_used": False,
        "source": event.source,
        "created_at": utcnow(),
    }


async def upsert_events(events: list[EconomicEvent]) -> int:
    written = 0
    if SessionLocal is None:
        for event in events:
            _memory_events[event.id] = event.model_dump(mode="json")
            written += 1
        return written
    async with SessionLocal() as session:
        for event in events:
            payload = _event_to_row(event)
            await session.merge(EconomicEventRow(**payload))
            written += 1
        await session.commit()
    return written


async def list_stored_events(start: datetime, end: datetime) -> list[EconomicEvent]:
    rows: list[dict[str, Any]] = []
    if SessionLocal is None:
        rows = list(_memory_events.values())
    else:
        async with SessionLocal() as session:
            result = await session.execute(
                select(EconomicEventRow).where(
                    EconomicEventRow.timestamp >= start,
                    EconomicEventRow.timestamp <= end,
                )
            )
            for row in result.scalars():
                rows.append(
                    {
                        "id": row.id,
                        "title": row.title,
                        "country": row.country,
                        "timestamp": row.timestamp,
                        "impact": row.impact,
                        "forecast": row.forecast,
                        "previous": row.previous,
                        "actual": row.actual,
                        "gold_impact": row.gold_impact,
                        "source": row.source,
                    }
                )
    out: list[EconomicEvent] = []
    for item in rows:
        try:
            out.append(EconomicEvent.model_validate(item))
        except Exception:
            continue
    return out


def filter_events(
    events: list[EconomicEvent],
    *,
    min_impact: str = "medium",
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[EconomicEvent]:
    floor = IMPACT_ORDER.get(min_impact, 2)
    out = []
    for event in events:
        if not is_usd_event(event.country):
            continue
        if IMPACT_ORDER.get(event.impact, 0) < floor:
            continue
        if start and event.timestamp < start:
            continue
        if end and event.timestamp > end:
            continue
        out.append(event)
    out.sort(key=lambda e: e.timestamp)
    return out


class EconomicCalendarService:
    def __init__(self, provider: EconomicCalendarProvider | None = None, ttl_seconds: float = 300.0):
        self.provider = provider or ForexFactoryProvider()
        self.ttl_seconds = ttl_seconds

    def _cache_ok(self) -> list[EconomicEvent] | None:
        global _cache
        if _cache is None:
            return None
        saved_at, events, _source = _cache
        if time.monotonic() - saved_at > self.ttl_seconds:
            return None
        return events

    async def fetch_window(
        self,
        start: datetime,
        end: datetime,
        *,
        min_impact: str = "medium",
        use_cache: bool = True,
    ) -> tuple[list[EconomicEvent], str, bool, str]:
        global _cache
        if use_cache:
            cached = self._cache_ok()
            if cached is not None:
                return filter_events(cached, min_impact=min_impact, start=start, end=end), _cache[2], True, ""

        try:
            events = await self.provider.fetch_events(start, end)
        except Exception as exc:
            logger.warning("Economic calendar provider failed: %s", exc)
            return [], "session-clock", False, str(exc)[:200]

        events = filter_events(events, min_impact=min_impact, start=start, end=end)
        _cache = (time.monotonic(), events, self.provider.name)
        try:
            await upsert_events(events)
        except Exception as exc:
            logger.debug("Calendar persist skipped: %s", exc)
        source = self.provider.name if events else "session-clock"
        return events, source, False, ""


def reset_calendar_cache() -> None:
    global _cache
    _cache = None
    _memory_events.clear()


calendar_service = EconomicCalendarService()


async def upcoming_events(hours_ahead: int = 24, min_impact: str = "medium") -> dict[str, Any]:
    now = utcnow()
    start = now - timedelta(hours=2)
    end = now + timedelta(hours=max(1, hours_ahead))
    service = calendar_service
    try:
        from app.services.settings_store import load_runtime_settings

        runtime = await load_runtime_settings()
        ttl = max(60, int(getattr(runtime, "economicCalendarCacheTtl", 5) or 5) * 60)
        provider_name = (getattr(runtime, "economicCalendarProvider", None) or "forex_factory").strip()
        if provider_name == "trading_economics":
            service = EconomicCalendarService(TradingEconomicsProvider(), ttl_seconds=ttl)
        else:
            service.ttl_seconds = ttl
    except Exception:
        pass
    events, source, cached, warning = await service.fetch_window(start, end, min_impact=min_impact)
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "source": source,
        "cached": cached,
        "warning": warning,
        "instrument": GOLD_INSTRUMENT,
        "hoursAhead": hours_ahead,
        "minImpact": min_impact,
    }
