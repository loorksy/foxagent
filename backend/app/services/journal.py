"""Decision journal + recommendation post-mortem."""

from __future__ import annotations

from typing import Any

from app.db import get_recommendation, update_recommendation
from app.schemas import new_id, utcnow

_ENTRIES: list[dict[str, Any]] = []


def reset_journal() -> None:
    _ENTRIES.clear()


async def write_postmortem(rec_id: str, body: dict[str, Any]) -> dict[str, Any]:
    rec = await get_recommendation(rec_id)
    if rec is None:
        return {"ok": False, "detail": "Recommendation not found"}
    note = {
        "thesis": str(body.get("thesis") or rec.get("rationale") or ""),
        "invalidation": str(body.get("invalidation") or ""),
        "outcome": str(body.get("outcome") or rec.get("status") or ""),
        "lesson": str(body.get("lesson") or ""),
        "at": utcnow().isoformat(),
    }
    rec["postmortem"] = note
    await update_recommendation(rec_id, {"postmortem": note})
    entry = {
        "id": new_id("jnl"),
        "kind": "recommendation",
        "sourceId": rec_id,
        "createdAt": note["at"],
        **note,
    }
    _ENTRIES.insert(0, entry)
    return {"ok": True, "entry": entry, "recommendation": rec}


def list_journal(limit: int = 50) -> list[dict[str, Any]]:
    return _ENTRIES[:limit]


def add_scan_journal(scan: dict[str, Any]) -> None:
    _ENTRIES.insert(0, {
        "id": new_id("jnl"),
        "kind": "scan",
        "sourceId": scan.get("id"),
        "createdAt": scan.get("createdAt"),
        "thesis": scan.get("thesis") or "",
        "outcome": f"accepted {scan.get('acceptedCount')} / rejected {scan.get('rejectedCount')}",
        "lesson": scan.get("error") or "",
    })
