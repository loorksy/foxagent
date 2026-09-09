"""Describe → warehouse backtest ≤8 → wait for a human pin. No invented candles."""

from __future__ import annotations

from typing import Any

from app.schemas import new_id, utcnow
from app.services.run_control import is_paused
from app.services.trading_bot.strategy_library import get_library
from app.services.trading_bot.strategy_schema import FLAG_TO_TRIGGER, SESSIONS, dsl_from_flags

MAX_ATTEMPTS = 8
_JOBS: dict[str, dict[str, Any]] = {}


def reset_experiment_jobs() -> None:
    _JOBS.clear()


def _mutate(conds: dict[str, Any], sessions: list[str], attempt: int) -> tuple[dict[str, Any], list[str], str]:
    flags = dict(conds)
    sess = list(sessions or SESSIONS)
    keys = list(FLAG_TO_TRIGGER)
    if attempt == 1:
        flags.setdefault("fvg_exists", True)
        return flags, sess, "ensure FVG condition"
    if attempt == 2:
        flags["asian_sweep"] = not flags.get("asian_sweep")
        return flags, sess, "toggle asian_sweep"
    if attempt == 3:
        flags["bos_confirmed"] = True
        return flags, sess, "require BOS"
    if attempt == 4:
        sess = ["london", "london_ny_overlap"]
        return flags, sess, "narrow to London / overlap"
    if attempt == 5:
        flags["breakout"] = True
        return flags, sess, "add range break"
    if attempt == 6:
        sess = list(SESSIONS)
        return flags, sess, "restore all sessions"
    flags["reversal"] = not flags.get("reversal")
    return flags, sess, "toggle reversal"


async def start_experiment(payload: dict[str, Any], *, engine_run=None) -> dict[str, Any]:
    if await is_paused():
        return {"ok": False, "paused": True, "detail": "FoxAgent is paused"}
    lib = get_library()
    body = dict(payload or {})
    body.setdefault("name", body.get("description") or "Gold experiment")
    proposed = await lib.propose(body, source="claude_proposed", created_by="claude")
    if not proposed.get("ok"):
        return proposed
    strategy = proposed["strategy"]
    job_id = new_id("job")
    job = {
        "id": job_id,
        "strategyId": strategy["id"],
        "status": "running",
        "attempts": [],
        "maxAttempts": MAX_ATTEMPTS,
        "createdAt": utcnow().isoformat(),
        "passed": False,
        "best": None,
    }
    _JOBS[job_id] = job
    conds = dict(strategy.get("entry_conditions") or {})
    sessions = list(strategy.get("sessions") or SESSIONS)
    for n in range(1, MAX_ATTEMPTS + 1):
        if await is_paused():
            job["status"] = "paused"
            break
        if n > 1:
            conds, sessions, change = _mutate(conds, sessions, n)
            current = await lib.get(strategy["id"])
            if current and current.status not in {"draft", "experimenting"}:
                current.status = "experimenting"
                await lib._persist(current)
            await lib.patch(
                strategy["id"],
                {"entry_conditions": conds, "sessions": sessions, "dsl": dsl_from_flags(conds, sessions)},
            )
        else:
            change = "initial draft"
        result = await lib.validate(strategy["id"], days=int(body.get("days") or 730), engine_run=engine_run)
        attempt = {
            "n": n,
            "change": change,
            "passed": bool(result.get("passed")),
            "reasons": result.get("reasons") or [],
            "strategy": result.get("strategy"),
            "report": {
                "winRate": (result.get("report") or {}).get("winRate") if isinstance(result.get("report"), dict) else getattr(result.get("report"), "winRate", None),
                "profitFactor": (result.get("report") or {}).get("profitFactor") if isinstance(result.get("report"), dict) else getattr(result.get("report"), "profitFactor", None),
                "maxDrawdownR": (result.get("report") or {}).get("maxDrawdownR") if isinstance(result.get("report"), dict) else getattr(result.get("report"), "maxDrawdownR", None),
                "totalTrades": (result.get("report") or {}).get("totalTrades") if isinstance(result.get("report"), dict) else getattr(result.get("report"), "totalTrades", None),
            },
        }
        job["attempts"].append(attempt)
        if result.get("passed"):
            job["passed"] = True
            job["best"] = attempt
            job["status"] = "awaiting_pin"
            break
        current = await lib.get(strategy["id"])
        if current:
            current.status = "experimenting"
            current.pinned = False
            await lib._persist(current)
        job["best"] = attempt
    else:
        job["status"] = "exhausted"
    current = await lib.get(strategy["id"])
    if current and current.status == "active":
        # Guard: validate must never pin.
        current.status = "validated"
        current.pinned = False
        await lib._persist(current)
    return {"ok": True, "job": job, "strategy": job.get("best", {}).get("strategy") or strategy}


def get_job(job_id: str) -> dict[str, Any] | None:
    return _JOBS.get(job_id)


def list_jobs() -> list[dict[str, Any]]:
    return sorted(_JOBS.values(), key=lambda j: j.get("createdAt") or "", reverse=True)
