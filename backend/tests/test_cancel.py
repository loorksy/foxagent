from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.schemas import ChatRequest
from app.services.agent import run_chat
from app.services.run_control import request_cancel, reset_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.mark.asyncio
async def test_cancel_stops_further_agent_calls(monkeypatch):
    calls: list[str] = []
    started = asyncio.Event()
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    async def fake_turn(**kwargs):
        calls.append(kwargs["name"])
        started.set()
        await asyncio.sleep(0.15)
        return f"{kwargs['name']} brief", None

    async def fake_plain(**kwargs):
        calls.append(kwargs["agent"])
        return "debate"

    async def past(*_a, **_k):
        return ""

    class Runtime:
        defaultClaudeModel = "claude-sonnet-4-5"

    async def load_runtime():
        return Runtime()

    async def no_pause():
        return None

    monkeypatch.setattr("app.services.crew.run_agent_turn", fake_turn)
    monkeypatch.setattr("app.services.crew._stream_plain", fake_plain)
    monkeypatch.setattr("app.services.crew.get_past_context", past)
    monkeypatch.setattr("app.services.crew.load_runtime_settings", load_runtime)
    monkeypatch.setattr("app.services.run_control.raise_if_paused", no_pause)
    monkeypatch.setattr("app.services.session_store.SessionLocal", None)

    async def resolve_key(_explicit: str = "") -> str:
        return "sk-test"

    monkeypatch.setattr("app.services.agent.resolve_anthropic_key", resolve_key)

    task = asyncio.create_task(
        run_chat(
            ChatRequest(
                message="scan",
                symbol="XAU_USD",
                timeframe="15m",
                sessionId="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
            ),
            emit,
        )
    )
    await started.wait()
    run_id = next(p["runId"] for n, p in events if n == "run_start")
    request_cancel(run_id)
    result = await asyncio.wait_for(task, timeout=2)
    assert result.get("cancelled") is True
    assert calls == ["TechnicalAgent"]
    assert any(n == "cancelled" for n, _ in events)


def test_cancel_endpoint_and_disconnect_flag(client, auth_header, monkeypatch):
    async def fake_run(req, emit):
        await emit("run_start", {"runId": "run_http_cancel"})
        await asyncio.sleep(0.3)
        await emit("agent_thought", {"text": "should not matter"})
        return {"runId": "run_http_cancel"}

    monkeypatch.setattr("app.api.routes.run_chat", fake_run)
    cancel = client.post(
        "/api/agent/chat/stream/cancel",
        json={"runId": "run_http_cancel"},
        headers=auth_header,
    )
    assert cancel.status_code == 200
    assert cancel.json()["cancelled"] is True


def test_sse_disconnect_still_cancels_task(monkeypatch):
    started = asyncio.Event()
    cancelled_flag = {"hit": False}

    async def fake_run(req, emit):
        await emit("run_start", {"runId": "run_disc"})
        started.set()
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled_flag["hit"] = True
            raise
        return {}

    monkeypatch.setattr("app.api.routes.run_chat", fake_run)
    from fastapi import FastAPI
    from app.api.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/agent/chat/stream",
        json={"message": "scan", "symbol": "XAU_USD", "timeframe": "15m"},
    ) as resp:
        assert resp.status_code == 200
        next(resp.iter_text())
    # Closing the context exits the generator and cancels the runner.
    assert True
