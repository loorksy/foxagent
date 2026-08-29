from __future__ import annotations

import os

import pytest

# Must be set before app.config.get_settings() is first constructed.
os.environ.setdefault("APP_PASSWORD", "test-operator-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-prod")
os.environ.setdefault("GOLD_WAREHOUSE_SYNC", "0")


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "test-operator-password")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-do-not-use-in-prod")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(auth_env):
    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def auth_cookie(client) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"password": "test-operator-password"})
    assert resp.status_code == 200
    token = resp.cookies.get("foxagent_token")
    assert token
    return {"foxagent_token": token}


@pytest.fixture
def auth_header(auth_cookie) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_cookie['foxagent_token']}"}
