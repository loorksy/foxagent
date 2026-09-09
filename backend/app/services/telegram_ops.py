"""Operational Telegram: briefing, stale/news alerts, allow-listed commands."""

from __future__ import annotations

import time
from typing import Any

from app.services.briefing import build_briefing, format_briefing_html
from app.services.telegram_service import parse_chat_ids, send_html

_RATE: dict[str, float] = {}
_SENT: set[str] = set()
COOLDOWN = {
    "briefing": 6 * 3600,
    "stale": 1800,
    "news": 1200,
    "scan": 900,
    "circuit": 900,
    "signal": 120,
}


def reset_telegram_ops() -> None:
    _RATE.clear()
    _SENT.clear()


def _allow(kind: str, key: str) -> bool:
    token = f"{kind}:{key}"
    if token in _SENT:
        return False
    now = time.time()
    last = _RATE.get(kind, 0)
    if now - last < COOLDOWN.get(kind, 600):
        return False
    _RATE[kind] = now
    _SENT.add(token)
    if len(_SENT) > 400:
        _SENT.clear()
        _SENT.add(token)
    return True


async def send_ops(kind: str, key: str, text: str) -> dict[str, Any]:
    if not _allow(kind, key):
        return {"ok": False, "skipped": True, "detail": "rate-limited"}
    from app.services.telegram_service import _telegram_credentials, telegram_ready

    token, chats, enabled = await _telegram_credentials()
    if not telegram_ready(token, chats, enabled):
        return {"ok": False, "skipped": True, "detail": "telegram off"}
    return await send_html(text, token=token, chat_ids=chats)


async def send_briefing() -> dict[str, Any]:
    body = await build_briefing()
    return {**await send_ops("briefing", body.get("generatedAt", "now")[:13], format_briefing_html(body)), "briefing": body}


async def maybe_alert_stale(stale: list[str]) -> dict[str, Any] | None:
    if not stale:
        return None
    return await send_ops("stale", ",".join(stale), f"Warehouse stale: {', '.join(stale)}\nhttps://foxagent.lork.cloud/inbox")


async def maybe_alert_news(title: str, minutes: int, event_id: str) -> dict[str, Any] | None:
    return await send_ops(
        "news",
        event_id,
        f"High-impact in {minutes}m: {title}\nhttps://foxagent.lork.cloud/calendar",
    )


ALLOWED_COMMANDS = {"/status", "/pause", "/resume", "/inbox"}


async def handle_command(text: str, chat_id: str) -> dict[str, Any]:
    from app.services.telegram_service import _telegram_credentials, parse_chat_ids

    _token, chats, _enabled = await _telegram_credentials()
    allowed = {str(item) for item in chats}
    if str(chat_id) not in allowed:
        return {"ok": False, "detail": "chat not allow-listed"}
    cmd = (text or "").strip().split()[0].lower()
    if cmd not in ALLOWED_COMMANDS:
        return {"ok": False, "detail": "unknown command"}
    from app.services.run_control import is_paused, set_paused
    from app.services.inbox import desk_status

    if cmd == "/pause":
        await set_paused(True)
        return {"ok": True, "command": cmd, "paused": True}
    if cmd == "/resume":
        await set_paused(False)
        return {"ok": True, "command": cmd, "paused": False}
    desk = await desk_status()
    return {"ok": True, "command": cmd, "desk": desk, "href": "https://foxagent.lork.cloud/inbox"}
