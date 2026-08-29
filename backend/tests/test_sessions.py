from __future__ import annotations

import pytest

from app.services.session_store import (
    append_session_event,
    create_session,
    ensure_session,
    get_session,
    is_session_id,
    list_sessions,
    normalize_session_id,
)


def test_accepts_uuid_and_bc_prefix():
    assert is_session_id("83c6842f-2de7-48ba-acd3-893e0be45f84")
    assert is_session_id("bc-83c6842f-2de7-48ba-acd3-893e0be45f84")
    assert not is_session_id("chat_abc")
    assert normalize_session_id("not-a-uuid") != "not-a-uuid"


@pytest.mark.asyncio
async def test_create_hydrate_and_restore_thread(monkeypatch):
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)
    session = await create_session("XAU_USD", "15m", "Gold scan", session_id="bc-83c6842f-2de7-48ba-acd3-893e0be45f84")
    assert session["id"] == "bc-83c6842f-2de7-48ba-acd3-893e0be45f84"
    await append_session_event(session["id"], "message", {"role": "user", "text": "scan gold"})
    await append_session_event(session["id"], "thought", {"agent": "TechnicalAgent", "text": "FVG at 2340"})
    await append_session_event(
        session["id"],
        "artifact",
        {"id": "art_1", "title": "ICT report", "type": "ict_report", "body": "# brief"},
    )
    await append_session_event(
        session["id"],
        "recommendation",
        {"id": "rec_1", "klineOverlays": [{"name": "priceLine", "points": []}]},
    )
    loaded = await get_session(session["id"])
    assert loaded is not None
    assert loaded["state"]["messages"][0]["text"] == "scan gold"
    assert loaded["state"]["thoughts"][0]["agent"] == "TechnicalAgent"
    assert loaded["state"]["artifacts"][0]["id"] == "art_1"
    assert loaded["state"]["recommendationId"] == "rec_1"
    assert loaded["state"]["overlays"]
    listed = await list_sessions()
    assert any(item["id"] == session["id"] for item in listed)


@pytest.mark.asyncio
async def test_ensure_session_is_idempotent(monkeypatch):
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)
    first = await ensure_session("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", "EUR_USD", "1h")
    second = await ensure_session("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", "EUR_USD", "1h")
    assert first["id"] == second["id"]
    assert first["symbol"] == "EUR_USD"


def test_session_http_routes(monkeypatch):
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    created = client.post(
        "/api/sessions",
        json={"id": "cccccccc-3333-4333-8333-cccccccccccc", "symbol": "XAU_USD", "title": "desk"},
    )
    assert created.status_code == 200
    sid = created.json()["id"]
    assert sid == "cccccccc-3333-4333-8333-cccccccccccc"
    fetched = client.get(f"/api/sessions/{sid}")
    assert fetched.status_code == 200
    listed = client.get("/api/sessions")
    assert any(item["id"] == sid for item in listed.json()["sessions"])
