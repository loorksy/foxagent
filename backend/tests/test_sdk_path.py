from __future__ import annotations

import logging
import sys
import types

import pytest

from app.services.sdk_runtime import stats as sdk_stats


def install_fake_sdk(monkeypatch, client_cls) -> None:
    """Point ClaudeSDKClient at a test double; stub the package if missing."""
    try:
        import claude_agent_sdk

        monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", client_cls)
        return
    except ImportError:
        pass

    class ClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    mod = types.ModuleType("claude_agent_sdk")
    mod.ClaudeSDKClient = client_cls
    mod.ClaudeAgentOptions = ClaudeAgentOptions
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", mod)


class _Text:
    def __init__(self, text: str) -> None:
        self.text = text
        self.type = "text"


class _Msg:
    def __init__(self, text: str) -> None:
        self.content = [_Text(text)]


class _FakeSDKClient:
    last_options = None
    last_prompt: object = None
    last_streamed: list = []
    fail_with: type[Exception] | None = None

    def __init__(self, options=None) -> None:
        type(self).last_options = options

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def query(self, prompt, session_id: str = "default") -> None:
        type(self).last_prompt = prompt
        type(self).last_streamed = []
        if self.fail_with:
            raise self.fail_with("simulated sdk failure")
        if hasattr(prompt, "__aiter__"):
            async for msg in prompt:
                type(self).last_streamed.append(msg)

    async def receive_response(self):
        yield _Msg("Technical brief complete. Bias BULLISH. FVG held at 2340.")


class CLIConnectionError(Exception):
    pass


@pytest.fixture(autouse=True)
def _reset_sdk_stats():
    sdk_stats.reset()
    _FakeSDKClient.fail_with = None
    _FakeSDKClient.last_prompt = None
    _FakeSDKClient.last_streamed = []
    yield
    sdk_stats.reset()


@pytest.mark.asyncio
async def test_sdk_path_forced_turn_completes_without_fallback(monkeypatch):
    install_fake_sdk(monkeypatch, _FakeSDKClient)
    monkeypatch.setattr("app.services.crew.try_build_sdk_server", lambda: object())

    anthropic_calls = {"n": 0}

    class Boom:
        def __init__(self, *a, **k):
            anthropic_calls["n"] += 1

    monkeypatch.setattr("anthropic.AsyncAnthropic", Boom)

    from app.services.crew import run_agent_turn

    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    text, rec = await run_agent_turn(
        name="TechnicalAgent",
        system="You are TechnicalAgent.",
        user="Analyze XAU_USD 15m",
        emit=emit,
        run_id="run_sdk",
        api_key="sk-test",
        model="claude-sonnet-4-5",
        session_id=None,
        require_sdk=True,
    )
    assert "FVG" in text
    assert rec is None
    assert anthropic_calls["n"] == 0
    assert sdk_stats.snapshot()["sdkPathSuccessCount"] == 1
    assert sdk_stats.snapshot()["sdkPathFallbackCount"] == 0
    assert any(name == "agent_thought" for name, _ in events)
    opts = _FakeSDKClient.last_options
    assert opts is not None
    assert "mcp__oanda__get_candles" in opts.allowed_tools
    assert "mcp__oanda__draw_on_chart" in opts.allowed_tools
    assert getattr(opts, "permission_mode", None) in {"dontAsk", "acceptEdits"}
    assert getattr(opts, "tools", None) in ([], None)
    assert getattr(opts, "strict_mcp_config", True) is True


@pytest.mark.asyncio
async def test_transient_sdk_failure_logs_and_increments_fallback(monkeypatch, caplog):
    _FakeSDKClient.fail_with = CLIConnectionError
    install_fake_sdk(monkeypatch, _FakeSDKClient)
    monkeypatch.setattr("app.services.crew.try_build_sdk_server", lambda: object())

    class _Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Messages:
        async def create(self, **_k):
            return _Stream()

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", _Client)

    from app.services.crew import run_agent_turn

    async def emit(_n, _p):
        return None

    caplog.set_level(logging.ERROR)
    text, _ = await run_agent_turn(
        name="TechnicalAgent",
        system="sys",
        user="ping",
        emit=emit,
        run_id="run_fb",
        api_key="sk-test",
        model="claude-sonnet-4-5",
        session_id=None,
    )
    snap = sdk_stats.snapshot()
    assert snap["sdkPathFallbackCount"] == 1
    assert snap["sdkPathSuccessCount"] == 0
    assert "CLIConnectionError" in snap["sdkPathLastFallbackReason"]
    assert any("SDK path failed, reason:" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_simulated_sdk_success_rate_over_twenty_turns(monkeypatch):
    install_fake_sdk(monkeypatch, _FakeSDKClient)
    monkeypatch.setattr("app.services.crew.try_build_sdk_server", lambda: object())

    from app.services.crew import run_agent_turn

    async def emit(_n, _p):
        return None

    for i in range(20):
        text, _ = await run_agent_turn(
            name="TechnicalAgent",
            system="sys",
            user=f"turn {i}",
            emit=emit,
            run_id=f"run_{i}",
            api_key="sk-test",
            model="claude-sonnet-4-5",
            session_id=None,
            require_sdk=True,
        )
        assert text
    snap = sdk_stats.snapshot()
    assert snap["sdkPathSuccessCount"] == 20
    assert snap["sdkPathFallbackCount"] == 0
    assert snap["sdkPathSuccessRate"] == 1.0


@pytest.mark.asyncio
async def test_config_error_does_not_fallback(monkeypatch):
    monkeypatch.setattr("app.services.crew.try_build_sdk_server", lambda: None)

    anthropic_calls = {"n": 0}

    class Boom:
        def __init__(self, *a, **k):
            anthropic_calls["n"] += 1

    monkeypatch.setattr("anthropic.AsyncAnthropic", Boom)

    from app.services.agent import AgentUnavailable
    from app.services.crew import run_agent_turn

    async def emit(_n, _p):
        return None

    with pytest.raises(AgentUnavailable, match="SDK MCP server"):
        await run_agent_turn(
            name="TechnicalAgent",
            system="sys",
            user="ping",
            emit=emit,
            run_id="run_cfg",
            api_key="sk-test",
            model="claude-sonnet-4-5",
            session_id=None,
        )
    snap = sdk_stats.snapshot()
    assert snap["sdkPathConfigErrorCount"] == 1
    assert snap["sdkPathFallbackCount"] == 0
    assert anthropic_calls["n"] == 0


def test_health_exposes_sdk_path_counters(client, auth_header, monkeypatch):
    async def fake_probe(*_a, **_k):
        return {"ok": True, "keyValid": True, "detail": "ok"}

    monkeypatch.setattr("app.api.routes.probe_anthropic", fake_probe)
    sdk_stats.record_success()
    sdk_stats.record_fallback("CLIConnectionError: simulated")
    resp = client.get("/api/health", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["sdkPathSuccessCount"] == 1
    assert body["sdkPathFallbackCount"] == 1
    assert body["sdkPathSuccessRate"] == 0.5
    assert "CLIConnectionError" in body["sdkPathLastFallbackReason"]


def test_classify_sdk_failure_splits_config_from_transient():
    from app.services.sdk_runtime import classify_sdk_failure

    class CLINotFoundError(Exception):
        pass

    class CLIConnectionError(Exception):
        pass

    assert classify_sdk_failure(CLINotFoundError("claude cli not found")) == "config"
    assert classify_sdk_failure(CLIConnectionError("broken pipe")) == "transient"
    assert classify_sdk_failure(RuntimeError("429 rate limit")) == "transient"
    assert classify_sdk_failure(TypeError("unexpected kwarg")) == "config"
