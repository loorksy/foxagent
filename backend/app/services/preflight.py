"""Operator-visible checks before the gold bot loop starts. Pause still wins."""

from __future__ import annotations

from typing import Any


def _check(id: str, ok: bool, *, blocking: bool, label: str, detail: str = "") -> dict[str, Any]:
    return {"id": id, "ok": ok, "blocking": blocking and not ok, "label": label, "detail": detail}


async def run_preflight() -> dict[str, Any]:
    from app.services.gold_warehouse import timeframe_health
    from app.services.run_control import is_paused
    from app.services.settings_store import load_runtime_settings
    from app.services.trading_bot import get_coordinator

    runtime = await load_runtime_settings()
    paused = await is_paused()
    snap = get_coordinator().snapshot()
    health = await timeframe_health()
    frames = health.get("timeframes") or {}
    stale_tfs = [tf for tf, row in frames.items() if (row or {}).get("stale")]
    oanda = bool(runtime.oandaApiToken and runtime.oandaAccountId)
    last_error = str(snap.get("lastError") or "")

    checks = [
        _check(
            "pause",
            not paused,
            blocking=True,
            label="Pause",
            detail="FoxAgent is paused — the bot will not scan until you resume" if paused else "Desk is live",
        ),
        _check(
            "warehouse",
            not stale_tfs,
            blocking=False,
            label="Gold warehouse",
            detail=("Stale: " + ", ".join(stale_tfs)) if stale_tfs else "Candles are fresh enough to scan",
        ),
        _check(
            "feed",
            oanda,
            blocking=False,
            label="Price feed",
            detail="OANDA credentials set" if oanda else "Simulator mode — no live broker feed",
        ),
        _check(
            "loop_error",
            not last_error,
            blocking=False,
            label="Last scan",
            detail=last_error or "No stored scan error",
        ),
    ]
    blocking = any(c["blocking"] for c in checks)
    return {
        "ok": not blocking,
        "blocking": blocking,
        "paused": paused,
        "botRunning": bool(snap.get("running")),
        "checks": checks,
    }
