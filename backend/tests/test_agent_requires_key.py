from __future__ import annotations

import pytest

from app.schemas import ChatRequest
from app.services import agent as agent_mod
from app.services.agent import run_chat


def test_algorithmic_fallback_removed():
    assert not hasattr(agent_mod, "run_algorithmic")


@pytest.mark.asyncio
async def test_run_chat_refuses_without_anthropic_key(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit(event: str, payload: dict) -> None:
        events.append((event, payload))

    async def no_key(_explicit: str = "") -> str:
        return ""

    monkeypatch.setattr("app.services.agent.resolve_anthropic_key", no_key)

    result = await run_chat(
        ChatRequest(message="scan gold", symbol="XAU_USD", timeframe="15m", model="sonnet"),
        emit,
    )
    assert result["recommendation"] is None
    assert result["engine"] is None
    assert "ANTHROPIC_API_KEY" in (result.get("error") or "")
    assert not any(name == "recommendation" for name, _ in events)
    assert any(name == "error" for name, _ in events)
