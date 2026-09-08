from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.economic_calendar import (
    EconomicCalendarService,
    ForexFactoryProvider,
    TradingEconomicsProvider,
    filter_events,
    infer_gold_impact,
    parse_forex_factory_html,
    reset_calendar_cache,
    upcoming_events,
)
from app.services.mcp_tools import dispatch_tool, tool_get_economic_calendar

FF_HTML = """
<table>
  <tr class="calendar__row calendar__row--day-breaker">
    <td class="calendar__date">Mon Sep 8</td>
  </tr>
  <tr class="calendar__row" data-event-id="ff-nfp">
    <td class="calendar__time">8:30am</td>
    <td class="calendar__currency">USD</td>
    <td class="calendar__impact"><span class="icon--ff-impact-red" title="High Impact Expected"></span></td>
    <td class="calendar__event">Non-Farm Employment Change</td>
    <td class="calendar__actual">180K</td>
    <td class="calendar__forecast">170K</td>
    <td class="calendar__previous">160K</td>
  </tr>
  <tr class="calendar__row">
    <td class="calendar__time">2:00am</td>
    <td class="calendar__currency">EUR</td>
    <td class="calendar__impact"><span class="icon--ff-impact-red" title="High"></span></td>
    <td class="calendar__event">CPI y/y</td>
    <td class="calendar__actual"></td>
    <td class="calendar__forecast">2.1%</td>
    <td class="calendar__previous">2.0%</td>
  </tr>
  <tr class="calendar__row">
    <td class="calendar__time">10:00am</td>
    <td class="calendar__currency">USD</td>
    <td class="calendar__impact"><span class="icon--ff-impact-yel" title="Low Impact Expected"></span></td>
    <td class="calendar__event">Treasury Refunding Announcement</td>
    <td class="calendar__actual"></td>
    <td class="calendar__forecast"></td>
    <td class="calendar__previous"></td>
  </tr>
</table>
"""


def test_forex_factory_provider_returns_events():
    events = parse_forex_factory_html(FF_HTML, week_start=datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert any(e.title.startswith("Non-Farm") for e in events)
    assert all(e.country == "USD" for e in events)
    assert infer_gold_impact("Non-Farm Employment Change", 180, 170) == "negative"


def test_calendar_filters_usd_events_only():
    events = parse_forex_factory_html(FF_HTML, week_start=datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert all(e.country == "USD" for e in events)
    kept = filter_events(events, min_impact="high")
    assert kept and all(e.impact in {"high", "critical"} for e in kept)


@pytest.mark.asyncio
async def test_calendar_caching_works():
    reset_calendar_cache()
    calls = {"n": 0}

    async def fake_html():
        calls["n"] += 1
        return FF_HTML

    service = EconomicCalendarService(ForexFactoryProvider(fetch_html=fake_html), ttl_seconds=60)
    start = datetime(2026, 9, 7, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, tzinfo=timezone.utc)
    first, source, cached, _ = await service.fetch_window(start, end, min_impact="medium", use_cache=True)
    second, _, cached2, _ = await service.fetch_window(start, end, min_impact="medium", use_cache=True)
    assert first and source == "forex_factory"
    assert cached is False
    assert cached2 is True
    assert calls["n"] == 1
    assert len(second) == len(first)
    reset_calendar_cache()


@pytest.mark.asyncio
async def test_calendar_fallback_on_error():
    reset_calendar_cache()

    async def boom():
        raise RuntimeError("blocked")

    service = EconomicCalendarService(ForexFactoryProvider(fetch_html=boom), ttl_seconds=60)
    start = datetime.now(timezone.utc)
    events, source, cached, warning = await service.fetch_window(start, start + timedelta(days=2))
    assert events == []
    assert source == "session-clock"
    assert cached is False
    assert "blocked" in warning
    reset_calendar_cache()


@pytest.mark.asyncio
async def test_trading_economics_skeleton():
    events = await TradingEconomicsProvider().fetch_events(
        datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert events == []


@pytest.mark.asyncio
async def test_calendar_mcp_tool():
    data = await tool_get_economic_calendar("XAU_USD", 24, "medium")
    assert "windows" in data
    assert data["source"] == "session-clock"
    assert data["events"] == []


@pytest.mark.asyncio
async def test_dispatch_still_honest_without_network():
    data = await dispatch_tool("get_economic_calendar", {"instrument": "XAU_USD"})
    assert data["source"] == "session-clock"
    assert "windows" in data
    assert "events" in data


@pytest.mark.asyncio
async def test_calendar_api_endpoint(client, auth_header):
    resp = client.get("/api/economic-calendar?hours_ahead=24&min_impact=medium", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    upcoming = client.get("/api/economic-calendar/upcoming", headers=auth_header)
    assert upcoming.status_code == 200


@pytest.mark.asyncio
async def test_upcoming_disabled_fetch():
    payload = await upcoming_events(24, "medium")
    assert payload["events"] == []
    assert payload["source"] == "session-clock"
