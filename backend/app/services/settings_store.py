from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import DATA_DIR, get_settings
from app.db import kv_get, kv_set
from app.schemas import SettingsPayload, SettingsPublic

KEY_FILE = DATA_DIR / ".foxagent.key"
SETTINGS_KV = "runtime_settings"


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.settings_secret or os.environ.get("SETTINGS_SECRET", "")
    if secret:
        digest = hashlib.sha256(secret.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    if KEY_FILE.exists():
        return Fernet(KEY_FILE.read_bytes())
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    try:
        os.chmod(KEY_FILE, 0o600)
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


async def save_runtime_settings(payload: SettingsPayload) -> SettingsPublic:
    token = _fernet().encrypt(payload.model_dump_json().encode()).decode()
    await kv_set(SETTINGS_KV, token)
    apply_runtime_to_env(payload)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    # restore applied values after cache clear by writing back onto new instance
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
    )


async def validate_anthropic_key(api_key: str) -> dict:
    if not api_key:
        return {"ok": False, "detail": "Missing key"}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        client.models.list()
        return {"ok": True, "detail": "Anthropic key accepted"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


async def validate_oanda(token: str, account_id: str, environment: str) -> dict:
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
