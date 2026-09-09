"""Per-strategy circuit. Manual Pause always wins."""

from __future__ import annotations

from typing import Any

from app.db import kv_get, kv_set

CIRCUIT_KEY = "strategy_circuits"
SAFE_KEY = "desk_safe_mode"
LOSS_LIMIT = 4
ERROR_LIMIT = 5

_errors = 0


def reset_circuits_memory() -> None:
    global _errors
    _errors = 0


async def _state() -> dict[str, Any]:
    raw = await kv_get(CIRCUIT_KEY)
    if not raw:
        return {}
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _save(state: dict[str, Any]) -> None:
    import json

    await kv_set(CIRCUIT_KEY, json.dumps(state))


async def is_halted(strategy_id: str) -> bool:
    if await is_safe_mode():
        return True
    row = (await _state()).get(strategy_id) or {}
    return bool(row.get("halted"))


async def halt(strategy_id: str, reason: str) -> dict[str, Any]:
    state = await _state()
    state[strategy_id] = {"halted": True, "reason": reason, "losses": int((state.get(strategy_id) or {}).get("losses") or 0)}
    await _save(state)
    return state[strategy_id]


async def resume_strategy(strategy_id: str) -> dict[str, Any]:
    state = await _state()
    state[strategy_id] = {"halted": False, "reason": "", "losses": 0}
    await _save(state)
    return state[strategy_id]


async def note_outcome(strategy_id: str, won: bool) -> dict[str, Any]:
    state = await _state()
    row = dict(state.get(strategy_id) or {"halted": False, "reason": "", "losses": 0})
    if won:
        row["losses"] = 0
    else:
        row["losses"] = int(row.get("losses") or 0) + 1
        if row["losses"] >= LOSS_LIMIT:
            row["halted"] = True
            row["reason"] = f"loss streak {row['losses']}"
    state[strategy_id] = row
    await _save(state)
    return row


async def snapshot() -> dict[str, Any]:
    return {"circuits": await _state(), "safeMode": await is_safe_mode(), "scanErrors": _errors}


async def is_safe_mode() -> bool:
    return (await kv_get(SAFE_KEY) or "") == "1"


async def set_safe_mode(on: bool) -> None:
    await kv_set(SAFE_KEY, "1" if on else "0")


async def note_scan_error() -> None:
    global _errors
    _errors += 1
    if _errors >= ERROR_LIMIT:
        await set_safe_mode(True)


async def clear_scan_error() -> None:
    global _errors
    _errors = 0
