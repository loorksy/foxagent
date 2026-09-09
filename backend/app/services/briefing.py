"""London briefing payload — same JSON for the web desk and Telegram."""

from __future__ import annotations

from typing import Any

from app.schemas import utcnow
from app.services.inbox import desk_status, list_items
from app.services.run_control import is_paused


async def build_briefing() -> dict[str, Any]:
    from app.services.economic_calendar import upcoming_events
    from app.services.gold_warehouse import timeframe_health
    from app.services.oanda import oanda
    from app.services.trading_bot import get_coordinator

    desk = await desk_status()
    items = await list_items()
    health = await timeframe_health()
    frames = health.get("timeframes") or {}
    stale = [tf for tf, row in frames.items() if (row or {}).get("stale")]
    cal = await upcoming_events(hours_ahead=24, min_impact="high")
    price = None
    try:
        tick = await oanda.get_live_price("XAU_USD")
        price = getattr(tick, "mid", None)
    except Exception:
        price = None
    snap = get_coordinator().snapshot()
    return {
        "generatedAt": utcnow().isoformat(),
        "symbol": "XAU_USD",
        "price": price,
        "paused": await is_paused(),
        "botRunning": bool(snap.get("running")),
        "warehouseStale": bool(stale),
        "staleTimeframes": stale,
        "pendingApprovals": sum(1 for i in items if i.get("tab") == "approvals"),
        "unlabeled": sum(1 for i in items if i.get("kind") == "recommendation"),
        "openInbox": len(items),
        "events24h": cal.get("events") or [],
        "calendarSource": cal.get("source") or "",
        "calendarWarning": cal.get("warning") or "",
        "desk": desk,
        "href": "/briefing",
        "inboxHref": "/inbox",
    }


def format_briefing_html(body: dict[str, Any]) -> str:
    events = body.get("events24h") or []
    titles = ", ".join(str(e.get("title") or "") for e in events[:6] if e.get("title")) or "none from source"
    stale = ", ".join(body.get("staleTimeframes") or []) or "fresh"
    return (
        "<b>FoxAgent briefing · XAU_USD</b>\n"
        f"Price: {body.get('price') or '—'}\n"
        f"Pause: {body.get('paused')} · Bot: {body.get('botRunning')}\n"
        f"Warehouse: {stale}\n"
        f"Pending: {body.get('pendingApprovals')} · Unlabeled: {body.get('unlabeled')}\n"
        f"High-impact 24h: {titles}\n"
        f'<a href="https://foxagent.lork.cloud/inbox">Inbox</a>'
    )
