"""Z.ai credentials and a real key probe. The key never leaves the server response."""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.services.model_catalog import DEFAULT_ZAI_MODEL
from app.services.settings_store import load_runtime_settings


async def resolve_zai_key(explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()
    runtime = await load_runtime_settings()
    return (runtime.zaiApiKey or get_settings().zai_api_key or "").strip()


def _sanitize(exc: Exception, api_key: str) -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text[:400]


def _probe_sync(api_key: str, model: str) -> dict:
    from zai import ZaiClient

    client = ZaiClient(api_key=api_key)
    response = client.chat.completions.create(
        model=model or DEFAULT_ZAI_MODEL,
        max_tokens=8,
        messages=[{"role": "user", "content": "Reply with the single word PONG"}],
    )
    message = response.choices[0].message
    content = getattr(message, "content", None)
    if not str(content or "").strip():
        return {"ok": False, "keyValid": True, "detail": "Z.ai accepted the key but returned an empty message"}
    return {"ok": True, "keyValid": True, "detail": "Z.ai key accepted and can create messages"}


async def probe_zai(api_key: str = "", *, model: str = "") -> dict:
    key = await resolve_zai_key(api_key)
    if not key:
        return {"ok": False, "keyValid": False, "detail": "Missing ZAI_API_KEY"}
    try:
        return await asyncio.to_thread(_probe_sync, key, model or DEFAULT_ZAI_MODEL)
    except Exception as exc:
        detail = _sanitize(exc, key)
        lowered = detail.lower()
        key_valid = True
        if any(token in lowered for token in ("authentication", "invalid api", "unauthorized", "api key")):
            key_valid = False
        return {"ok": False, "keyValid": key_valid, "detail": detail}
