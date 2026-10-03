from __future__ import annotations

import json

import pytest

from app.schemas import ChatRequest
from app.services.agent import run_chat
from app.services.model_catalog import is_zai_model, list_models, provider_for_model, resolve_model
from app.services.zai_chat import run_zai_chat


def test_operator_can_choose_zai_without_replacing_claude():
    assert resolve_model("sonnet") == "claude-sonnet-4-5"
    assert resolve_model("glm") == "glm-5.3"
    assert resolve_model("zai") == "glm-5.3"
    assert is_zai_model("glm-5.3-flash")
    assert not is_zai_model("claude-opus-4-5")
    assert provider_for_model("glm-5.2") == "zai"
    assert provider_for_model("haiku") == "anthropic"
    ids = {row["id"]: row["provider"] for row in list_models()}
    assert ids["claude-sonnet-4-5"] == "anthropic"
    assert ids["glm-5.3"] == "zai"


@pytest.mark.asyncio
async def test_zai_chat_uses_official_client_and_tools(monkeypatch):
    calls: list[dict] = []

    class _Message:
        def __init__(self, content: str = "", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
            self.reasoning_content = ""
            self.role = "assistant"

        def model_dump(self, exclude_none: bool = True):
            data = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                data["tool_calls"] = self.tool_calls
            return data

    class _Response:
        def __init__(self, message):
            self.choices = [type("Choice", (), {"message": message})()]
            self.usage = type("Usage", (), {"prompt_tokens": 4, "completion_tokens": 2})()

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _Response(
                    _Message(
                        tool_calls=[
                            {
                                "id": "call_price",
                                "type": "function",
                                "function": {
                                    "name": "memory_recall",
                                    "arguments": json.dumps({"query": "London", "instrument": "XAU_USD"}),
                                },
                            }
                        ]
                    )
                )
            return _Response(_Message(content="Stored London preference is still on the desk."))

    class _Client:
        def __init__(self, api_key: str):
            assert api_key == "zai-test-key"
            self.chat = type("Chat", (), {"completions": _Completions()})()

    import zai

    monkeypatch.setattr(zai, "ZaiClient", _Client)

    async def no_session(_session_id: str):
        return None

    async def no_journal(*_a, **_k):
        return ""

    monkeypatch.setattr("app.services.session_store.get_session", no_session)
    monkeypatch.setattr("app.services.memory_log.get_past_context", no_journal)
    monkeypatch.setattr("app.db.SessionLocal", None)
    from app.services import long_term_memory as mem

    mem._fallback.clear()
    await mem.capture_memory(text="London sweep first.", layer="L2", kind="scenario", symbol="XAU_USD")

    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    _rec, text = await run_zai_chat(
        ChatRequest(message="ما الذي تتذكره عن لندن؟", symbol="XAU_USD", timeframe="15m", model="glm"),
        emit,
        "run_zai",
        "zai-test-key",
        "sess_zai",
    )
    assert text == "Stored London preference is still on the desk."
    assert calls[0]["model"] == "glm-5.3"
    assert any(tool["function"]["name"] == "memory_recall" for tool in calls[0]["tools"])
    assert any(name == "agent_tool_call" and payload.get("name") == "memory_recall" for name, payload in events)
    blob = json.dumps(events)
    assert "zai-test-key" not in blob


@pytest.mark.asyncio
async def test_missing_zai_key_does_not_call_the_client(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("ZaiClient must not be constructed without a key")

    import zai

    monkeypatch.setattr(zai, "ZaiClient", boom)

    async def no_key(_explicit: str = "") -> str:
        return ""

    async def claude_key(_explicit: str = "") -> str:
        return "sk-ant-present"

    monkeypatch.setattr("app.services.zai_runtime.resolve_zai_key", no_key)
    monkeypatch.setattr("app.services.agent.resolve_anthropic_key", claude_key)

    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    result = await run_chat(
        ChatRequest(message="سعر الذهب", symbol="XAU_USD", timeframe="15m", model="glm-5.3"),
        emit,
    )
    assert result["engine"] is None
    assert "ZAI_API_KEY" in (result.get("error") or "")
    assert "sk-ant-present" not in json.dumps(events)


@pytest.mark.asyncio
async def test_claude_path_still_requires_anthropic_key(monkeypatch):
    async def no_key(_explicit: str = "") -> str:
        return ""

    async def zai_key(_explicit: str = "") -> str:
        return "zai-present"

    monkeypatch.setattr("app.services.agent.resolve_anthropic_key", no_key)
    monkeypatch.setattr("app.services.zai_runtime.resolve_zai_key", zai_key)

    async def emit(_name: str, _payload: dict) -> None:
        return None

    result = await run_chat(
        ChatRequest(message="scan gold", symbol="XAU_USD", timeframe="15m", model="sonnet"),
        emit,
    )
    assert "ANTHROPIC_API_KEY" in (result.get("error") or "")
    assert "ZAI_API_KEY" not in (result.get("error") or "")


def test_env_example_documents_empty_zai_key():
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath(".env.example").read_text(encoding="utf-8")
    assert "ZAI_API_KEY=" in text
    assert "ZAI_API_KEY=sk" not in text
    assert "ZAI_API_KEY=zai" not in text
