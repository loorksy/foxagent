from __future__ import annotations

import pytest

from app.schemas import SettingsPayload
from app.services import metaapi


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    """Matches URL fragments to canned responses."""

    routes: dict[str, FakeResponse] = {}
    last_trade: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def _match(self, url: str) -> FakeResponse:
        for fragment, resp in self.routes.items():
            if fragment in url:
                return resp
        return FakeResponse(404, {}, "not found")

    async def get(self, url: str, **kwargs) -> FakeResponse:
        return await self._match(url)

    async def post(self, url: str, **kwargs) -> FakeResponse:
        FakeAsyncClient.last_trade = kwargs.get("json")
        return await self._match(url)


def _runtime(token: str = "", account_id: str = ""):
    async def load() -> SettingsPayload:
        payload = SettingsPayload()
        payload.metaapiToken = token
        payload.metaapiAccountId = account_id
        return payload

    return load


async def test_status_unconfigured(monkeypatch):
    monkeypatch.setattr(metaapi, "load_runtime_settings", _runtime())
    status = await metaapi.get_status()
    assert status["connected"] is False
    assert status["configured"] is False


async def test_status_connected_uses_region_client(monkeypatch):
    metaapi.reset_region_cache()
    monkeypatch.setattr(metaapi, "load_runtime_settings", _runtime("tok", "acc-1"))
    FakeAsyncClient.routes = {
        "mt-provisioning-api-v1": FakeResponse(
            200,
            {"state": "DEPLOYED", "connectionStatus": "CONNECTED", "name": "Demo MT5", "region": "london"},
        ),
        "account-information": FakeResponse(200, {"balance": 100.5, "equity": 99.25, "currency": "USD"}),
    }
    monkeypatch.setattr(metaapi.httpx, "AsyncClient", FakeAsyncClient)
    status = await metaapi.get_status()
    assert status["connected"] is True
    assert status["configured"] is True
    assert status["accountName"] == "Demo MT5"
    assert status["balance"] == 100.5
    assert status["currency"] == "USD"


async def test_status_undeployed_is_disconnected(monkeypatch):
    metaapi.reset_region_cache()
    monkeypatch.setattr(metaapi, "load_runtime_settings", _runtime("tok", "acc-2"))
    FakeAsyncClient.routes = {
        "mt-provisioning-api-v1": FakeResponse(
            200, {"state": "UNDEPLOYED", "connectionStatus": "DISCONNECTED", "region": "new-york"}
        ),
    }
    monkeypatch.setattr(metaapi.httpx, "AsyncClient", FakeAsyncClient)
    status = await metaapi.get_status()
    assert status["connected"] is False
    assert status["configured"] is True
    assert "not deployed" in status["detail"].lower()


async def test_place_order_requires_config(monkeypatch):
    monkeypatch.setattr(metaapi, "load_runtime_settings", _runtime())
    result = await metaapi.place_market_order("XAUUSD", "BUY", 0.01)
    assert "error" in result


async def test_place_order_posts_trade(monkeypatch):
    metaapi.reset_region_cache()
    monkeypatch.setattr(metaapi, "load_runtime_settings", _runtime("tok", "acc-3"))
    FakeAsyncClient.routes = {
        "mt-provisioning-api-v1": FakeResponse(200, {"state": "DEPLOYED", "region": "new-york"}),
        "/trade": FakeResponse(200, {"numericCode": 10009, "stringCode": "TRADE_RETCODE_DONE", "orderId": "1"}),
    }
    FakeAsyncClient.last_trade = None
    monkeypatch.setattr(metaapi.httpx, "AsyncClient", FakeAsyncClient)
    result = await metaapi.place_market_order("XAUUSD", "sell", 0.02, stop_loss=2400.0, take_profit=2300.0)
    assert result.get("stringCode") == "TRADE_RETCODE_DONE"
    assert FakeAsyncClient.last_trade == {
        "actionType": "ORDER_TYPE_SELL",
        "symbol": "XAUUSD",
        "volume": 0.02,
        "comment": "FoxAgent",
        "stopLoss": 2400.0,
        "takeProfit": 2300.0,
    }


def test_mt5_status_endpoint_unconfigured(client, auth_cookie, monkeypatch):
    monkeypatch.setattr(metaapi, "load_runtime_settings", _runtime())
    resp = client.get("/api/mt5/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["configured"] is False


def test_settings_roundtrip_masks_metaapi_token(client, auth_cookie):
    resp = client.put(
        "/api/settings",
        json={"metaapiToken": "secret-metaapi-token-123", "metaapiAccountId": "acc-uuid-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "secret-metaapi-token-123" not in resp.text
    assert "metaapiToken" not in data
    assert data["metaapiTokenSet"] is True
    assert data["metaapiAccountId"] == "acc-uuid-1"
    assert data["metaapiConfigured"] is True

    got = client.get("/api/settings")
    assert got.status_code == 200
    assert "secret-metaapi-token-123" not in got.text
    assert got.json()["metaapiTokenSet"] is True


def test_validate_target_metaapi(client, auth_cookie, monkeypatch):
    async def fake_validate(token: str = "", account_id: str = "") -> dict:
        assert token == "tok-x"
        assert account_id == "acc-x"
        return {"ok": True, "connected": True, "balance": 55.0, "currency": "USD", "detail": "MT5 connected"}

    monkeypatch.setattr("app.services.metaapi.validate_metaapi", fake_validate)
    resp = client.post(
        "/api/settings/validate",
        json={"target": "metaapi", "metaapiToken": "tok-x", "metaapiAccountId": "acc-x"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["connected"] is True
