"""Operator inbox: staged gold signals, unlabeled recs, and desk alerts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db import kv_get, kv_set, list_recommendations
from app.schemas import utcnow
from app.services.risk_rules import RiskRejected
from app.services.trading_bot.promote import promote_signal
from app.services.trading_bot.store import get_signal, list_signals, update_signal

ACK_KEY = "inbox_acks"
OPEN_SIGNAL = {"pending", "staged"}
UNLABELED_REC = {"PENDING", "pending"}
NEWS_MINUTES = 30


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        stamp = raw
    else:
        text = str(raw).replace("Z", "+00:00")
        try:
            stamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


async def _acked() -> set[str]:
    raw = await kv_get(ACK_KEY)
    if not raw:
        return set()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(data, list):
        return set()
    return {str(x) for x in data}


async def _store_acks(ids: set[str]) -> None:
    await kv_set(ACK_KEY, json.dumps(sorted(ids)))


def reset_inbox_acks_memory() -> None:
    """Tests call this after resetting the KV memory store."""


async def ack_item(item_id: str) -> dict[str, Any]:
    item = await get_item(item_id)
    if item is None:
        return {"ok": False, "detail": "Not found"}
    if item.get("tab") == "approvals":
        return {"ok": False, "detail": "Approvals must be approved or rejected"}
    ids = await _acked()
    ids.add(item_id)
    await _store_acks(ids)
    return {"ok": True, "id": item_id, "acked": True}


def _item(
    *,
    item_id: str,
    tab: str,
    kind: str,
    title: str,
    summary: str,
    severity: str,
    href: str,
    source_href: str,
    created_at: str | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "tab": tab,
        "kind": kind,
        "title": title,
        "summary": summary,
        "severity": severity,
        "href": href,
        "sourceHref": source_href,
        "createdAt": created_at,
        "payload": payload or {},
    }


async def _signal_items() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sig in await list_signals(80):
        status = str(sig.get("status") or "")
        if status not in OPEN_SIGNAL:
            continue
        if str((sig.get("metadata") or {}).get("mode") or sig.get("mode") or "") == "alert":
            continue  # alerts-bot signals are notification-only, never approvals
        sid = str(sig.get("id") or "")
        side = str(sig.get("signalType") or "").upper()
        title = f"{sig.get('strategyId') or 'signal'} · {side}"
        summary = (
            f"XAU_USD {sig.get('timeframe')} · "
            f"in {sig.get('entryPrice')} · SL {sig.get('stopLoss')} · "
            f"R {sig.get('riskReward')} · {(float(sig.get('confidence') or 0) * 100):.0f}%"
        )
        out.append(
            _item(
                item_id=f"signal:{sid}",
                tab="approvals",
                kind="signal",
                title=title,
                summary=summary,
                severity="high" if float(sig.get("confidence") or 0) >= 0.8 else "medium",
                href=f"/inbox/signal:{sid}",
                source_href="/bot",
                created_at=sig.get("createdAt"),
                payload={"signal": sig},
            )
        )
    return out


async def _recommendation_items() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in await list_recommendations(80):
        status = str(rec.get("status") or "")
        if status not in UNLABELED_REC:
            continue
        rid = str(rec.get("id") or "")
        setup = rec.get("tradeSetup") or {}
        action = setup.get("action") or rec.get("sentiment") or ""
        out.append(
            _item(
                item_id=f"rec:{rid}",
                tab="inbox",
                kind="recommendation",
                title=f"Unlabeled recommendation · {action}",
                summary=str(rec.get("rationale") or "Pending operator label")[:180],
                severity="medium",
                href=f"/inbox/rec:{rid}",
                source_href="/recommendations",
                created_at=str(rec.get("timestamp") or "") or None,
                payload={"recommendation": rec},
            )
        )
    return out


async def _warehouse_item() -> dict[str, Any] | None:
    from app.services.gold_warehouse import timeframe_health

    health = await timeframe_health()
    frames = health.get("timeframes") or {}
    stale = [tf for tf, row in frames.items() if (row or {}).get("stale")]
    if not stale:
        return None
    return _item(
        item_id="warehouse:stale",
        tab="alerts",
        kind="warehouse",
        title="Gold warehouse stale",
        summary="Freshness failed on " + ", ".join(stale),
        severity="high",
        href="/inbox/warehouse:stale",
        source_href="/settings",
        created_at=utcnow().isoformat(),
        payload={"timeframes": stale, "health": health},
    )


async def _news_items() -> list[dict[str, Any]]:
    from app.services.economic_calendar import upcoming_events

    payload = await upcoming_events(hours_ahead=6, min_impact="high")
    now = utcnow()
    out: list[dict[str, Any]] = []
    for ev in payload.get("events") or []:
        stamp = _parse_dt(ev.get("timestamp"))
        if stamp is None:
            continue
        minutes = (stamp - now).total_seconds() / 60.0
        if minutes < 0 or minutes > NEWS_MINUTES:
            continue
        eid = str(ev.get("id") or "event")
        title = str(ev.get("title") or "USD event")
        out.append(
            _item(
                item_id=f"news:{eid}",
                tab="alerts",
                kind="news",
                title=f"High-impact event in {int(minutes)}m",
                summary=title,
                severity="high",
                href=f"/inbox/news:{eid}",
                source_href="/calendar",
                created_at=stamp.isoformat(),
                payload={"event": ev, "minutes": int(minutes)},
            )
        )
    return out


async def _bot_error_item() -> dict[str, Any] | None:
    from app.services.trading_bot import get_coordinator

    snap = get_coordinator().snapshot()
    err = str(snap.get("lastError") or "").strip()
    if not err:
        return None
    return _item(
        item_id="bot:error",
        tab="alerts",
        kind="bot",
        title="Last scan failed",
        summary=err[:240],
        severity="high",
        href="/inbox/bot:error",
        source_href="/bot",
        created_at=utcnow().isoformat(),
        payload={"snapshot": snap},
    )


async def list_items(*, include_acked: bool = False) -> list[dict[str, Any]]:
    hidden = set() if include_acked else await _acked()
    items: list[dict[str, Any]] = []
    items.extend(await _signal_items())
    items.extend(await _recommendation_items())
    warehouse = await _warehouse_item()
    if warehouse:
        items.append(warehouse)
    items.extend(await _news_items())
    bot_err = await _bot_error_item()
    if bot_err:
        items.append(bot_err)
    visible = [i for i in items if i["id"] not in hidden]
    visible.sort(key=lambda i: i.get("createdAt") or "", reverse=True)
    return visible


async def get_item(item_id: str) -> dict[str, Any] | None:
    for item in await list_items(include_acked=True):
        if item["id"] == item_id:
            return item
    if item_id.startswith("signal:"):
        sig = await get_signal(item_id.split(":", 1)[1])
        if not sig:
            return None
        reason = (sig.get("metadata") or {}).get("rejectionReason")
        return _item(
            item_id=item_id,
            tab="approvals",
            kind="signal",
            title=f"{sig.get('strategyId')} · {sig.get('status')}",
            summary=str(reason or sig.get("status") or ""),
            severity="low",
            href=f"/inbox/{item_id}",
            source_href="/bot",
            created_at=sig.get("createdAt"),
            payload={"signal": sig, "rejectionReason": reason},
        )
    return None


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    approvals = sum(1 for i in items if i.get("tab") == "approvals")
    alerts = sum(1 for i in items if i.get("tab") == "alerts")
    inbox = sum(1 for i in items if i.get("tab") == "inbox")
    return {
        "open": len(items),
        "inbox": inbox,
        "approvals": approvals,
        "alerts": alerts,
    }


async def desk_status() -> dict[str, Any]:
    from app.services.economic_calendar import upcoming_events
    from app.services.gold_warehouse import timeframe_health
    from app.services.run_control import is_paused
    from app.services.settings_store import load_runtime_settings
    from app.services.trading_bot import get_coordinator

    runtime = await load_runtime_settings()
    snap = get_coordinator().snapshot()
    health = await timeframe_health()
    frames = health.get("timeframes") or {}
    stale = any((row or {}).get("stale") for row in frames.values())
    items = await list_items()
    next_title = None
    next_minutes = None
    try:
        payload = await upcoming_events(hours_ahead=24, min_impact="high")
        now = utcnow()
        best: tuple[float, str] | None = None
        for ev in payload.get("events") or []:
            stamp = _parse_dt(ev.get("timestamp"))
            if stamp is None:
                continue
            minutes = (stamp - now).total_seconds() / 60.0
            if minutes < 0:
                continue
            title = str(ev.get("title") or "USD event")
            if best is None or minutes < best[0]:
                best = (minutes, title)
        if best:
            next_minutes = int(best[0])
            next_title = best[1]
    except Exception:
        next_title = None
    return {
        "paused": await is_paused(),
        "botRunning": bool(snap.get("running")),
        "botEnabled": bool(runtime.botEnabled),
        "warehouseStale": stale,
        "nextEventTitle": next_title,
        "nextEventMinutes": next_minutes,
        "openCount": len(items),
        "lastError": str(snap.get("lastError") or ""),
    }


async def snapshot(tab: str | None = None) -> dict[str, Any]:
    items = await list_items()
    if tab in {"inbox", "approvals", "alerts"}:
        items = [i for i in items if i.get("tab") == tab]
    return {"items": items, "counts": _counts(await list_items()), "desk": await desk_status()}


def _signal_id(item_id: str) -> str:
    if item_id.startswith("signal:"):
        return item_id.split(":", 1)[1]
    return item_id


async def approve_signal(item_id: str) -> dict[str, Any]:
    sid = _signal_id(item_id)
    signal = await get_signal(sid)
    if signal is None:
        return {"ok": False, "detail": "Signal not found"}
    if str((signal.get("metadata") or {}).get("mode") or signal.get("mode") or "") == "alert":
        return {"ok": False, "detail": "إشارة تنبيه فقط — لا تدخل قائمة الموافقات"}
    if str(signal.get("status") or "") not in OPEN_SIGNAL | {"pending"}:
        return {"ok": False, "detail": f"Signal is {signal.get('status')}, not staged"}
    try:
        result = await promote_signal(sid)
    except RiskRejected as exc:
        return {"ok": False, "detail": str(exc), "reasons": (exc.result or {}).get("reasons") or []}
    if result.get("ok"):
        result["itemId"] = f"signal:{sid}"
        try:
            from app.services.trading_bot.instances import execute_signal_order

            order = await execute_signal_order(sid, trigger="approval")
            if order is not None:
                result["order"] = order
        except Exception:
            result.setdefault("order", None)
    return result


async def reject_signal(item_id: str, reason: str) -> dict[str, Any]:
    sid = _signal_id(item_id)
    signal = await get_signal(sid)
    if signal is None:
        return {"ok": False, "detail": "Signal not found"}
    text = (reason or "").strip()
    if not text:
        return {"ok": False, "detail": "Rejection reason is required"}
    extra = dict(signal.get("metadata") or {})
    extra["rejectionReason"] = text
    extra["rejectedAt"] = utcnow().isoformat()
    updated = await update_signal(sid, {"status": "rejected", "metadata": extra})
    return {"ok": True, "itemId": f"signal:{sid}", "signal": updated}
