from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import DATA_DIR, get_settings
from app.db import kv_get, kv_set
from app.schemas import SettingsPayload, SettingsPublic

KEY_FILE = DATA_DIR / ".foxagent.key"
SETTINGS_KV = "runtime_settings"
_PROBE_TTL_SEC = 120.0
_probe_cache: tuple[float, str, dict] | None = None


def _data_root() -> Path:
    override = os.environ.get("FOXAGENT_DATA_DIR", "").strip()
    if override:
        return Path(override)
    volume = Path("/data")
    if volume.is_dir() and os.access(volume, os.W_OK):
        return volume
    return DATA_DIR


def _key_candidates() -> list[Path]:
    root = _data_root()
    paths = [root / ".foxagent.key"]
    if KEY_FILE not in paths:
        paths.append(KEY_FILE)
    return paths


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.settings_secret or os.environ.get("SETTINGS_SECRET", "")
    if secret:
        digest = hashlib.sha256(secret.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    for path in _key_candidates():
        if not path.exists():
            continue
        raw = path.read_bytes()
        durable = _data_root() / ".foxagent.key"
        if path != durable:
            try:
                durable.parent.mkdir(parents=True, exist_ok=True)
                if not durable.exists():
                    durable.write_bytes(raw)
                    os.chmod(durable, 0o600)
            except OSError:
                pass
        return Fernet(raw)
    key = Fernet.generate_key()
    dest = _data_root() / ".foxagent.key"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(key)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return Fernet(key)


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••" + value[-4:]


async def load_runtime_settings() -> SettingsPayload:
    env = get_settings()
    raw = await kv_get(SETTINGS_KV)
    stored = SettingsPayload()
    if raw:
        try:
            stored = SettingsPayload.model_validate_json(_fernet().decrypt(raw.encode()).decode())
        except (InvalidToken, ValueError, json.JSONDecodeError):
            try:
                stored = SettingsPayload.model_validate_json(raw)
            except Exception:
                stored = SettingsPayload()
    return SettingsPayload(
        anthropicApiKey=stored.anthropicApiKey or env.anthropic_api_key,
        oandaApiToken=stored.oandaApiToken or env.oanda_api_token,
        oandaAccountId=stored.oandaAccountId or env.oanda_account_id,
        oandaEnvironment=stored.oandaEnvironment or env.oanda_environment,  # type: ignore[arg-type]
        defaultClaudeModel=stored.defaultClaudeModel or env.default_claude_model,
        maxRiskPercent=stored.maxRiskPercent or env.max_risk_percent,
        minRiskReward=stored.minRiskReward or env.min_risk_reward,
        allowedSessions=stored.allowedSessions or [s.strip() for s in env.allowed_sessions.split(",") if s.strip()],
        telegramBotToken=stored.telegramBotToken or env.telegram_bot_token,
        telegramChatId=stored.telegramChatId or env.telegram_chat_id,
        enableTelegramNotifications=(
            stored.enableTelegramNotifications if raw else env.enable_telegram_notifications
        ),
    )


def apply_runtime_to_env(payload: SettingsPayload) -> None:
    """Push runtime secrets into the cached Settings object used by connectors."""
    env = get_settings()
    env.anthropic_api_key = payload.anthropicApiKey
    env.oanda_api_token = payload.oandaApiToken
    env.oanda_account_id = payload.oandaAccountId
    env.oanda_environment = payload.oandaEnvironment
    env.default_claude_model = payload.defaultClaudeModel
    env.max_risk_percent = payload.maxRiskPercent
    env.min_risk_reward = payload.minRiskReward
    env.allowed_sessions = ",".join(payload.allowedSessions)
    env.telegram_bot_token = payload.telegramBotToken
    env.telegram_chat_id = payload.telegramChatId
    env.enable_telegram_notifications = payload.enableTelegramNotifications


async def save_runtime_settings(payload: SettingsPayload) -> SettingsPublic:
    current = await load_runtime_settings()
    if not payload.anthropicApiKey:
        payload.anthropicApiKey = current.anthropicApiKey
    if not payload.oandaApiToken:
        payload.oandaApiToken = current.oandaApiToken
    if not payload.telegramBotToken:
        payload.telegramBotToken = current.telegramBotToken
    token = _fernet().encrypt(payload.model_dump_json().encode()).decode()
    await kv_set(SETTINGS_KV, token)
    apply_runtime_to_env(payload)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    apply_runtime_to_env(payload)
    return to_public(payload)


def to_public(payload: SettingsPayload) -> SettingsPublic:
    env = get_settings()
    return SettingsPublic(
        anthropicApiKeySet=bool(payload.anthropicApiKey),
        oandaApiTokenSet=bool(payload.oandaApiToken),
        oandaAccountId=payload.oandaAccountId,
        oandaEnvironment=payload.oandaEnvironment,
        defaultClaudeModel=payload.defaultClaudeModel,
        maxRiskPercent=payload.maxRiskPercent,
        minRiskReward=payload.minRiskReward,
        allowedSessions=payload.allowedSessions,
        oandaConfigured=bool(payload.oandaApiToken and payload.oandaAccountId),
        anthropicConfigured=bool(payload.anthropicApiKey),
        dataMode="oanda" if (payload.oandaApiToken and payload.oandaAccountId) else "simulator",
        telegramBotTokenSet=bool(payload.telegramBotToken),
        telegramChatId=payload.telegramChatId,
        enableTelegramNotifications=payload.enableTelegramNotifications,
        telegramConfigured=bool(payload.telegramBotToken and payload.telegramChatId),
    )


async def resolve_anthropic_key(explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()
    runtime = await load_runtime_settings()
    return (runtime.anthropicApiKey or get_settings().anthropic_api_key or "").strip()


def _sanitize_anthropic_error(exc: Exception, api_key: str) -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text[:400]


def _probe_anthropic_sync(api_key: str, live_completion: bool) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    client.models.list()
    if not live_completion:
        return {"ok": True, "keyValid": True, "detail": "Anthropic key accepted"}
    model = get_settings().default_claude_model or "claude-sonnet-4-5"
    client.messages.create(
        model=model,
        max_tokens=8,
        messages=[{"role": "user", "content": "Reply with the single word PONG"}],
    )
    return {"ok": True, "keyValid": True, "detail": "Anthropic key accepted and can create messages"}


async def probe_anthropic(
    api_key: str = "",
    *,
    live_completion: bool = True,
    use_cache: bool = False,
) -> dict:
    key = await resolve_anthropic_key(api_key)
    if not key:
        return {"ok": False, "keyValid": False, "detail": "Missing ANTHROPIC_API_KEY"}
    global _probe_cache
    cache_token = f"{key[-8:]}:{int(live_completion)}"
    now = time.monotonic()
    if use_cache and _probe_cache:
        cached_at, token, payload = _probe_cache
        if token == cache_token and now - cached_at < _PROBE_TTL_SEC:
            return payload
    try:
        payload = await asyncio.to_thread(_probe_anthropic_sync, key, live_completion)
    except Exception as exc:
        detail = _sanitize_anthropic_error(exc, key)
        lowered = detail.lower()
        key_valid = "credit balance" in lowered or "too low to access" in lowered
        if "authentication" in lowered or "invalid x-api-key" in lowered or "invalid api key" in lowered:
            key_valid = False
        payload = {"ok": False, "keyValid": key_valid, "detail": detail}
    if use_cache:
        _probe_cache = (now, cache_token, payload)
    return payload


async def validate_anthropic_key(api_key: str = "") -> dict:
    return await probe_anthropic(api_key, live_completion=True, use_cache=False)


async def validate_oanda(token: str, account_id: str, environment: str) -> dict:
    runtime = await load_runtime_settings()
    token = token or runtime.oandaApiToken
    account_id = account_id or runtime.oandaAccountId
    environment = environment or runtime.oandaEnvironment
    if not token or not account_id:
        return {"ok": False, "detail": "Token and account id required"}
    import httpx

    base = (
        "https://api-fxtrade.oanda.com"
        if environment == "live"
        else "https://api-fxpractice.oanda.com"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base}/v3/accounts/{account_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return {"ok": True, "detail": "OANDA account reachable"}
            return {"ok": False, "detail": f"OANDA HTTP {resp.status_code}: {resp.text[:180]}"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
