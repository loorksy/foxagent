from __future__ import annotations

import time

import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from app.auth import COOKIE_NAME, PUBLIC_API_PATHS, issue_token
from app.config import get_settings

DUMMY = {
    "rec_id": "rec_missing",
    "session_id": "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
}

# Bodies so authenticated calls get past request parsing after the auth gate.
BODIES = {
    ("PATCH", "/api/recommendations/{rec_id}"): {"status": "CANCELLED"},
    ("POST", "/api/sessions"): {"symbol": "XAU_USD", "timeframe": "15m"},
    ("PUT", "/api/sessions/{session_id}"): {"title": "desk"},
    ("PUT", "/api/settings"): {"maxRiskPercent": 1.0, "minRiskReward": 2.0, "allowedSessions": ["london"]},
    ("POST", "/api/settings/validate"): {"target": "unknown"},
    ("POST", "/api/agent/chat"): {"message": "ping", "symbol": "XAU_USD", "timeframe": "15m"},
    ("POST", "/api/agent/chat/stream"): {"message": "ping", "symbol": "XAU_USD", "timeframe": "15m"},
    ("POST", "/api/auth/login"): {"password": "test-operator-password"},
}


def _fill(path: str) -> str:
    for key, value in DUMMY.items():
        path = path.replace("{" + key + "}", value)
    return path


def _protected_http_routes(app) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path, ops in app.openapi()["paths"].items():
        if not path.startswith("/api/") or path in PUBLIC_API_PATHS:
            continue
        for method in sorted(ops):
            if method.lower() in {"head", "options"}:
                continue
            found.append((method.upper(), path))
    return found


def test_every_api_route_is_401_without_token(client):
    routes = _protected_http_routes(client.app)
    assert routes, "expected protected /api routes on the app"
    failures: list[str] = []
    for method, path in routes:
        resp = client.request(method, _fill(path), json=BODIES.get((method, path)))
        if resp.status_code != 401:
            failures.append(f"{method} {path} -> {resp.status_code} {resp.text[:160]}")
    assert not failures, "unauthenticated calls must be 401:\n" + "\n".join(failures)


def test_every_api_route_accepts_valid_token(client, auth_header, monkeypatch):
    async def fake_run(req, emit):
        await emit("assistant", {"text": "ok"})
        return {"runId": "run_auth", "recommendation": None}

    async def fake_probe(*_a, **_k):
        return {"ok": True, "keyValid": True, "detail": "ok"}

    monkeypatch.setattr("app.api.routes.run_chat", fake_run)
    monkeypatch.setattr("app.api.routes.probe_anthropic", fake_probe)
    monkeypatch.setattr("app.services.settings_store.probe_anthropic", fake_probe)
    routes = _protected_http_routes(client.app)
    failures: list[str] = []
    for method, path in routes:
        resp = client.request(method, _fill(path), json=BODIES.get((method, path)), headers=auth_header)
        if resp.status_code == 401:
            failures.append(f"{method} {path} -> 401 {resp.text[:160]}")
    assert not failures, "valid token must not be rejected:\n" + "\n".join(failures)


def test_login_then_cookie_reaches_protected_route(client, monkeypatch):
    async def fake_probe(*_a, **_k):
        return {"ok": True, "keyValid": True, "detail": "ok"}

    monkeypatch.setattr("app.api.routes.probe_anthropic", fake_probe)
    denied = client.get("/api/health")
    assert denied.status_code == 401
    login = client.post("/api/auth/login", json={"password": "test-operator-password"})
    assert login.status_code == 200
    assert login.cookies.get(COOKIE_NAME)
    allowed = client.get("/api/health")
    assert allowed.status_code == 200
    settings = client.get("/api/settings")
    assert settings.status_code == 200


def test_invalid_token_is_rejected(client):
    resp = client.get("/api/health", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


def test_expired_token_is_rejected(client, auth_env):
    token = issue_token(expires_minutes=-1)
    # PyJWT may reject negative TTL at encode time; force an expired payload if needed.
    if not token or jwt.decode(token, options={"verify_signature": False, "verify_exp": False}).get("exp", 1) > time.time():
        token = jwt.encode(
            {"sub": "operator", "exp": int(time.time()) - 30},
            get_settings().jwt_secret,
            algorithm="HS256",
        )
    resp = client.get("/api/health", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()


def test_wrong_password_is_rejected(client):
    resp = client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 401


def test_ws_market_rejects_without_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/market"):
            pass


def test_ws_market_accepts_valid_token(client, auth_header):
    with client.websocket_connect("/ws/market", headers=auth_header) as ws:
        ws.send_text("ping")
