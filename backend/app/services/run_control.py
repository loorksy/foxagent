"""In-process cancellation and global pause for agent runs."""

from __future__ import annotations

import time
from typing import Any

from app.db import kv_get, kv_set

PAUSE_KEY = "system_paused"

_cancelled: set[str] = set()
_paused_memory = False


class RunCancelled(Exception):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Run {run_id} cancelled")


class SystemPaused(Exception):
    def __init__(self) -> None:
        super().__init__("FoxAgent is paused")


def reset_for_tests() -> None:
    _cancelled.clear()
    global _paused_memory
    _paused_memory = False


def request_cancel(run_id: str) -> bool:
    if not run_id:
        return False
    _cancelled.add(run_id)
    return True


def is_cancelled(run_id: str | None) -> bool:
    return bool(run_id and run_id in _cancelled)


def raise_if_cancelled(run_id: str | None) -> None:
    if is_cancelled(run_id):
        raise RunCancelled(run_id or "")


def clear_cancel(run_id: str | None) -> None:
    if run_id:
        _cancelled.discard(run_id)


async def set_paused(paused: bool) -> bool:
    global _paused_memory
    _paused_memory = paused
    await kv_set(PAUSE_KEY, "1" if paused else "0")
    return paused


async def is_paused() -> bool:
    stored = await kv_get(PAUSE_KEY)
    if stored is None:
        return _paused_memory
    return stored.strip() in {"1", "true", "yes", "on"}


async def raise_if_paused() -> None:
    if await is_paused():
        raise SystemPaused()


class DebateBudget:
    def __init__(self, max_rounds: int = 2, max_seconds: float = 90.0) -> None:
        self.max_rounds = max_rounds
        self.deadline = time.monotonic() + max_seconds
        self.calls = 0

    def allow_another(self) -> bool:
        if self.calls >= self.max_rounds * 2:
            return False
        if time.monotonic() >= self.deadline:
            return False
        return True

    def mark(self) -> None:
        self.calls += 1
