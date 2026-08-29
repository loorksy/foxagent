from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.services.mcp_tools import dispatch_tool, mcp_tool_specs, tool_capture_chart_screenshot, tool_draw_on_chart
from app.services.sdk_runtime import vision_user_content


def _png_ok(data: bytes) -> None:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 2000


@pytest.mark.asyncio
async def test_capture_produces_real_png(tmp_path):
    b64 = await tool_capture_chart_screenshot("XAU_USD", "M15", 80)
    raw = base64.b64decode(b64)
    _png_ok(raw)
    sample = tmp_path / "chart-sample.png"
    sample.write_bytes(raw)
    assert sample.stat().st_size > 2000


@pytest.mark.asyncio
async def test_full_analysis_sends_official_image_content_block(monkeypatch):
    captured: dict = {}

    async def no_sdk(**_k):
        return None

    monkeypatch.setattr("app.services.crew._try_sdk_turn", no_sdk)

    class _Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Messages:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return _Stream()

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", _Client)

    from app.services.crew import run_agent_turn

    b64 = await tool_capture_chart_screenshot("XAU_USD", "M15", 80)

    async def emit(_n, _p):
        return None

    await run_agent_turn(
        name="TechnicalAgent",
        system="sys",
        user="Analyze 15m liquidity pools and map FVG.",
        emit=emit,
        run_id="run_vis",
        api_key="sk-test",
        model="claude-sonnet-4-5",
        session_id=None,
        image_b64=b64,
    )
    content = captured["messages"][0]["content"]
    assert isinstance(content, list)
    image = next(block for block in content if block["type"] == "image")
    source = image["source"]
    assert source["type"] == "base64"
    assert source["media_type"] == "image/png"
    raw = base64.b64decode(source["data"])
    _png_ok(raw)


@pytest.mark.asyncio
async def test_full_crew_invokes_capture_before_technical_turn(monkeypatch):
    turns: list[dict] = []

    async def fake_turn(**kwargs):
        turns.append(kwargs)
        if kwargs["name"] == "RiskManagerAgent":
            from app.services.agent import AgentUnavailable

            raise AgentUnavailable("stop-after-vision")
        return "brief", None

    async def fake_debate(**_k):
        return "bull", "bear"

    monkeypatch.setattr("app.services.crew.run_agent_turn", fake_turn)
    monkeypatch.setattr("app.services.crew._run_debate", fake_debate)
    monkeypatch.setattr("app.services.session_store.get_session", lambda *_a, **_k: None)

    from app.schemas import ChatRequest
    from app.services.agent import AgentUnavailable
    from app.services.crew import _run_crew_body

    async def emit(_n, _p):
        return None

    req = ChatRequest(message="Analyze 15m liquidity pools and give a setup.", symbol="XAU_USD", timeframe="15m")
    with pytest.raises(AgentUnavailable, match="stop-after-vision"):
        await _run_crew_body(req, emit, "run_vis2", "sk-test", "sid")
    tech = next(t for t in turns if t["name"] == "TechnicalAgent")
    assert tech["image_b64"]
    _png_ok(base64.b64decode(tech["image_b64"]))


@pytest.mark.asyncio
async def test_quick_question_skips_forced_vision(monkeypatch):
    turns: list[dict] = []

    async def fake_turn(**kwargs):
        turns.append(kwargs)
        if kwargs["name"] == "RiskManagerAgent":
            from app.services.agent import AgentUnavailable

            raise AgentUnavailable("stop")
        return "brief", None

    async def fake_debate(**_k):
        return "bull", "bear"

    monkeypatch.setattr("app.services.crew.run_agent_turn", fake_turn)
    monkeypatch.setattr("app.services.crew._run_debate", fake_debate)
    monkeypatch.setattr("app.services.session_store.get_session", lambda *_a, **_k: None)

    from app.schemas import ChatRequest
    from app.services.agent import AgentUnavailable
    from app.services.crew import _run_crew_body

    async def emit(_n, _p):
        return None

    req = ChatRequest(message="What is XAUUSD current trend?", symbol="XAU_USD", timeframe="15m")
    with pytest.raises(AgentUnavailable):
        await _run_crew_body(req, emit, "run_q", "sk-test", "sid")
    tech = next(t for t in turns if t["name"] == "TechnicalAgent")
    assert not tech.get("image_b64")


@pytest.mark.asyncio
async def test_draw_on_chart_emits_additive_overlays():
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    result = await tool_draw_on_chart(
        [
            {
                "name": "rect",
                "points": [
                    {"timestamp": 1_700_000_000_000, "value": 2340.0},
                    {"timestamp": 1_700_000_900_000, "value": 2344.0},
                ],
                "styles": {"fillColor": "rgba(34,197,94,0.18)"},
                "annotationText": "FVG",
            }
        ],
        emit,
    )
    assert result["ok"] is True
    assert result["additive"] is True
    assert result["overlays"][0]["name"] == "rect"
    assert events[0][0] == "agent_chart_overlays"
    assert events[0][1]["overlays"][0]["annotationText"] == "FVG"

    dispatched = await dispatch_tool(
        "draw_on_chart",
        {"overlays": [{"name": "priceLine", "points": [{"timestamp": 1, "value": 10}]}]},
        emit,
    )
    assert dispatched["ok"] is True


def test_vision_user_content_matches_official_block_shape():
    block = vision_user_content("read this", "aGVsbG8=")
    assert block[0]["type"] == "image"
    assert block[0]["source"] == {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}
    assert block[1] == {"type": "text", "text": "read this"}


@pytest.mark.asyncio
async def test_sdk_path_forwards_official_image_block(monkeypatch):
    from tests.test_sdk_path import _FakeSDKClient, install_fake_sdk

    install_fake_sdk(monkeypatch, _FakeSDKClient)
    monkeypatch.setattr("app.services.crew.try_build_sdk_server", lambda: object())

    from app.services.crew import run_agent_turn

    b64 = await tool_capture_chart_screenshot("XAU_USD", "M15", 80)

    async def emit(_n, _p):
        return None

    await run_agent_turn(
        name="TechnicalAgent",
        system="sys",
        user="Analyze 15m liquidity pools and map FVG.",
        emit=emit,
        run_id="run_sdk_vis",
        api_key="sk-test",
        model="claude-sonnet-4-5",
        session_id=None,
        image_b64=b64,
        require_sdk=True,
    )
    streamed = _FakeSDKClient.last_streamed
    assert streamed, "SDK query must stream a user message when a chart image is attached"
    content = streamed[0]["message"]["content"]
    image = next(block for block in content if block["type"] == "image")
    source = image["source"]
    assert source["type"] == "base64"
    assert source["media_type"] == "image/png"
    _png_ok(base64.b64decode(source["data"]))


def test_draw_on_chart_is_registered_for_both_paths():
    names = {spec["name"] for spec in mcp_tool_specs()}
    assert "draw_on_chart" in names
    from app.services.sdk_runtime import SDK_TOOLS

    assert "mcp__oanda__draw_on_chart" in SDK_TOOLS


def test_frontend_consumes_draw_on_chart_overlays():
    root = Path(__file__).resolve().parents[2]
    send = (root / "frontend/src/lib/agentSend.ts").read_text(encoding="utf-8")
    workspace = (root / "frontend/src/stores/workspace.ts").read_text(encoding="utf-8")
    canvas = (root / "frontend/src/components/ChartCanvas.tsx").read_text(encoding="utf-8")
    overlays = (root / "frontend/src/lib/overlays.ts").read_text(encoding="utf-8")
    assert 'type === "agent_chart_overlays"' in send
    assert "appendToChart" in send
    assert 'type: "append"' in workspace
    assert "appendToChart:" in workspace
    assert 'command.type === "append"' in canvas
    assert "applyOverlays(chart, command.overlays" in canvas
    assert "export async function applyOverlays" in overlays
