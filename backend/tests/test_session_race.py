from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.memory_log import decision_summary
from app.services.session_store import append_session_event, create_session, get_session


@pytest.mark.asyncio
async def test_client_put_does_not_drop_server_thoughts(monkeypatch):
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)
    session = await create_session("XAU_USD", "15m", "race", session_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
    await append_session_event(session["id"], "thought", {"agent": "TechnicalAgent", "text": "FVG held"})

    from app.api.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    stale = client.put(
        f"/api/sessions/{session['id']}",
        json={
            "title": "client title",
            "state": {
                "messages": [{"role": "user", "text": "hi"}],
                "thoughts": [],
                "tools": [],
                "debate": [],
                "overlays": [{"name": "priceLine", "points": []}],
            },
        },
    )
    assert stale.status_code == 200
    loaded = await get_session(session["id"])
    assert loaded is not None
    assert loaded["title"] == "client title"
    assert loaded["state"]["thoughts"][0]["text"] == "FVG held"
    assert loaded["state"]["overlays"]
    assert loaded["state"].get("messages") in (None, [], loaded["state"].get("messages"))
    assert not loaded["state"].get("messages")


def test_memory_decision_is_a_reference_not_a_full_payload():
    text = decision_summary(recommendation_id="rec_abc", symbol="XAU_USD", action="BUY", rating="BULLISH")
    assert "rec_abc" in text
    assert "XAU_USD" in text
    assert "entryPrice" not in text
    assert "klineOverlays" not in text
    assert "rationale" not in text
    assert "{" not in text
