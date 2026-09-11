"""MetaApi cloud (metaapi.cloud) REST client for MT5 accounts.

Endpoints used:
- Provisioning API (global):
  GET https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts/{accountId}
  -> account metadata: name, region, state (DEPLOYED/...), connectionStatus (CONNECTED/...)
- Client API (regional):
  GET  https://mt-client-api-v1.{region}.agiliumtrade.ai/users/current/accounts/{accountId}/account-information
  POST https://mt-client-api-v1.{region}.agiliumtrade.ai/users/current/accounts/{accountId}/trade

All functions are fail-closed: they return structured dicts and never raise
into route handlers.
"""

from __future__ import annotations

import time

import httpx

from app.services.settings_store import load_runtime_settings

PROVISIONING_BASE = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
_TIMEOUT = 10.0
_REGION_TTL_SEC = 300.0

# accountId -> (monotonic timestamp, region)
_region_cache: dict[str, tuple[float, str]] = {}


def reset_region_cache() -> None:
    _region_cache.clear()


def _client_base(region: str) -> str:
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"


def _headers(token: str) -> dict[str, str]:
    return {"auth-token": token, "Accept": "application/json"}


async def _resolve_credentials(token: str = "", account_id: str = "") -> tuple[str, str]:
    token = (token or "").strip()
    account_id = (account_id or "").strip()
    if token and account_id:
        return token, account_id
    runtime = await load_runtime_settings()
    return token or runtime.metaapiToken, account_id or runtime.metaapiAccountId


async def _fetch_account(client: httpx.AsyncClient, token: str, account_id: str) -> dict:
    resp = await client.get(
        f"{PROVISIONING_BASE}/users/current/accounts/{account_id}",
        headers=_headers(token),
    )
    if resp.status_code != 200:
        return {"error": f"MetaApi provisioning HTTP {resp.status_code}: {resp.text[:180]}"}
    return resp.json()


async def _resolve_region(client: httpx.AsyncClient, token: str, account_id: str) -> str | dict:
    """Return the cached region for the account, or an error dict."""
    now = time.monotonic()
    cached = _region_cache.get(account_id)
    if cached and now - cached[0] < _REGION_TTL_SEC:
        return cached[1]
    account = await _fetch_account(client, token, account_id)
    if "error" in account:
        return account
    region = str(account.get("region") or "new-york")
    _region_cache[account_id] = (now, region)
    return region


async def get_status(token: str = "", account_id: str = "") -> dict:
    """Read MT5 account status via MetaApi. Never raises."""
    token, account_id = await _resolve_credentials(token, account_id)
    if not token or not account_id:
        return {
            "connected": False,
            "configured": False,
            "state": "",
            "accountName": "",
            "balance": None,
            "equity": None,
            "currency": "",
            "detail": "MetaApi token/account not configured",
        }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            account = await _fetch_account(client, token, account_id)
            if "error" in account:
                return {
                    "connected": False,
                    "configured": True,
                    "state": "",
                    "accountName": "",
                    "balance": None,
                    "equity": None,
                    "currency": "",
                    "detail": account["error"],
                }
            state = str(account.get("state") or "")
            connection_status = str(account.get("connectionStatus") or "")
            name = str(account.get("name") or "")
            region = str(account.get("region") or "new-york")
            _region_cache[account_id] = (time.monotonic(), region)
            base = {
                "connected": False,
                "configured": True,
                "state": state,
                "connectionStatus": connection_status,
                "accountName": name,
                "balance": None,
                "equity": None,
                "currency": "",
            }
            if state != "DEPLOYED":
                base["detail"] = f"Account not deployed (state={state or 'unknown'})"
                return base
            info_resp = await client.get(
                f"{_client_base(region)}/users/current/accounts/{account_id}/account-information",
                headers=_headers(token),
            )
            if info_resp.status_code != 200:
                base["detail"] = f"MetaApi client HTTP {info_resp.status_code}: {info_resp.text[:180]}"
                return base
            info = info_resp.json()
            base.update(
                connected=connection_status == "CONNECTED",
                balance=info.get("balance"),
                equity=info.get("equity"),
                currency=str(info.get("currency") or ""),
                detail="MT5 account reachable"
                if connection_status == "CONNECTED"
                else f"Terminal not connected (connectionStatus={connection_status or 'unknown'})",
            )
            return base
    except Exception as exc:
        return {
            "connected": False,
            "configured": True,
            "state": "",
            "accountName": "",
            "balance": None,
            "equity": None,
            "currency": "",
            "detail": str(exc)[:300],
        }


async def is_connected() -> bool:
    status = await get_status()
    return bool(status.get("connected"))


async def validate_metaapi(token: str = "", account_id: str = "") -> dict:
    """Validate candidate credentials for the settings validate endpoint."""
    status = await get_status(token, account_id)
    if not status.get("configured"):
        return {"ok": False, "configured": False, "detail": "MetaApi token and account id required"}
    if status.get("connected"):
        balance = status.get("balance")
        currency = status.get("currency") or ""
        return {
            "ok": True,
            "detail": f"MT5 connected — balance {balance} {currency}".strip(),
            **status,
        }
    return {"ok": False, "detail": str(status.get("detail") or "Not connected"), **status}


async def place_market_order(
    symbol: str,
    side: str,
    volume: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    comment: str = "FoxAgent",
) -> dict:
    """Execute a market order via the MetaApi client API.

    NOT wired into any agent/bot flow yet — reserved for the future
    execution bot.
    """
    token, account_id = await _resolve_credentials()
    if not token or not account_id:
        return {"error": "MetaApi token/account not configured"}
    side_norm = (side or "").strip().upper()
    if side_norm not in {"BUY", "SELL"}:
        return {"error": f"Invalid side: {side!r} (expected BUY or SELL)"}
    trade: dict = {
        "actionType": f"ORDER_TYPE_{side_norm}",
        "symbol": symbol,
        "volume": float(volume),
        "comment": comment[:26],
    }
    if stop_loss is not None:
        trade["stopLoss"] = float(stop_loss)
    if take_profit is not None:
        trade["takeProfit"] = float(take_profit)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            region = await _resolve_region(client, token, account_id)
            if isinstance(region, dict):
                return region
            resp = await client.post(
                f"{_client_base(region)}/users/current/accounts/{account_id}/trade",
                headers=_headers(token),
                json=trade,
            )
            if resp.status_code not in (200, 201):
                return {"error": f"MetaApi trade HTTP {resp.status_code}: {resp.text[:300]}"}
            return resp.json()
    except Exception as exc:
        return {"error": str(exc)[:300]}
