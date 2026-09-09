"""Persist every gold-bot cycle, even when no signal survives."""

from __future__ import annotations

from typing import Any

from app.schemas import new_id, utcnow

_SCANS: list[dict[str, Any]] = []
_LISTENERS: list = []


def reset_scans() -> None:
    _SCANS.clear()


def add_listener(fn) -> None:
    _LISTENERS.append(fn)


async def emit_scan_event(event: str, payload: dict[str, Any]) -> None:
    body = {"type": event, "payload": payload}
    for fn in list(_LISTENERS):
        try:
            await fn(body)
        except Exception:
            pass
    try:
        from app.api.ws import bot_hub

        await bot_hub.broadcast(body)
    except Exception:
        pass


async def record_scan(*, agents: list[str], accepted: list[dict[str, Any]], rejected: int, error: str = "") -> dict[str, Any]:
    row = {
        "id": new_id("scan"),
        "createdAt": utcnow().isoformat(),
        "agents": agents,
        "accepted": [s.get("id") for s in accepted],
        "acceptedCount": len(accepted),
        "rejectedCount": rejected,
        "error": error,
        "thesis": "cycle recorded even with zero signals",
    }
    _SCANS.insert(0, row)
    del _SCANS[400:]
    await emit_scan_event("scan_complete", row)
    try:
        from app.services.journal import add_scan_journal

        add_scan_journal(row)
    except Exception:
        pass
    return row


def list_scans(limit: int = 40) -> list[dict[str, Any]]:
    return _SCANS[:limit]


def get_scan(scan_id: str) -> dict[str, Any] | None:
    return next((s for s in _SCANS if s["id"] == scan_id), None)
