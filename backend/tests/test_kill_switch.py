from __future__ import annotations

import pytest

from app.db import _memory_settings
from app.schemas import ChatRequest
from app.services.agent import run_chat
from app.services.run_control import reset_for_tests, set_paused


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr("app.db.SessionLocal", None)
    _memory_settings.clear()
    yield
    reset_for_tests()
    _memory_settings.clear()


@pytest.mark.asyncio
async def test_run_chat_refuses_when_paused_with_zero_llm_calls(monkeypatch):
    calls = {"n": 0}

    async def boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("LLM should not be called while paused")

    monkeypatch.setattr("app.services.agent.resolve_anthropic_key", boom)
    monkeypatch.setattr("app.services.crew.run_crew", boom)
    await set_paused(True)
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    result = await run_chat(ChatRequest(message="scan", symbol="XAU_USD", timeframe="15m"), emit)
    assert result.get("paused") is True
    assert "paused" in (result.get("error") or "").lower()
    assert calls["n"] == 0
    assert any(p.get("paused") for n, p in events if n == "error")


@pytest.mark.asyncio
async def test_pause_then_resume_allows_run(monkeypatch):
    await set_paused(True)
    await set_paused(False)

    async def fake_crew(req, emit, run_id, api_key, session_id):
        return None

    async def key(_explicit: str = "") -> str:
        return "sk-test"

    monkeypatch.setattr("app.services.agent.resolve_anthropic_key", key)
    monkeypatch.setattr("app.services.crew.run_crew", fake_crew)
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)

    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    result = await run_chat(ChatRequest(message="scan", symbol="XAU_USD", timeframe="15m"), emit)
    assert result.get("paused") is not True
    assert result.get("error") is None or "paused" not in str(result.get("error")).lower()


def test_pause_and_resume_http_then_chat_refused(client, auth_header, monkeypatch):
    state = {"paused": False}

    async def fake_set(paused: bool) -> bool:
        state["paused"] = paused
        return paused

    async def fake_is() -> bool:
        return state["paused"]

    async def fake_raise() -> None:
        from app.services.run_control import SystemPaused

        if state["paused"]:
            raise SystemPaused()

    monkeypatch.setattr("app.api.routes.set_paused", fake_set)
    monkeypatch.setattr("app.api.routes.is_paused", fake_is)
    monkeypatch.setattr("app.services.run_control.is_paused", fake_is)
    monkeypatch.setattr("app.services.run_control.set_paused", fake_set)
    monkeypatch.setattr("app.services.run_control.raise_if_paused", fake_raise)

    paused = client.post("/api/system/pause", headers=auth_header)
    assert paused.status_code == 200
    assert paused.json()["paused"] is True
    status = client.get("/api/system/status", headers=auth_header)
    assert status.json()["paused"] is True

    async def fake_run(req, emit):
        from app.services.run_control import raise_if_paused

        await raise_if_paused()
        return {"ok": True}

    monkeypatch.setattr("app.api.routes.run_chat", fake_run)
    stream = client.post(
        "/api/agent/chat/stream",
        json={"message": "scan", "symbol": "XAU_USD", "timeframe": "15m"},
        headers=auth_header,
    )
    assert stream.status_code == 200
    assert "paused" in stream.text.lower() or "FoxAgent is paused" in stream.text

    resumed = client.post("/api/system/resume", headers=auth_header)
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False

    async def ok_run(req, emit):
        await emit("assistant", {"text": "ok"})
        return {"ok": True}

    monkeypatch.setattr("app.api.routes.run_chat", ok_run)
    stream2 = client.post(
        "/api/agent/chat/stream",
        json={"message": "scan", "symbol": "XAU_USD", "timeframe": "15m"},
        headers=auth_header,
    )
    assert stream2.status_code == 200
    assert "paused" not in stream2.text.lower() or "assistant" in stream2.text
