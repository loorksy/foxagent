from __future__ import annotations

import pytest

from app.services.crew import last_working_phrase
from app.services.mcp_tools import compact_tool_output, emit_tool_result


def test_last_working_phrase_takes_final_line():
    assert last_working_phrase("أراجع شارت الربع ساعة") == "أراجع شارت الربع ساعة"
    assert last_working_phrase("long brief\n\nأقرأ الأخبار") == "أقرأ الأخبار"
    assert last_working_phrase("") == ""


def test_compact_tool_output_strips_png():
    out = compact_tool_output("capture_chart_screenshot", "a" * 200)
    assert out == {"image": "png", "bytes": 200}
    assert compact_tool_output("draw_on_chart", {"ok": True, "image": "x" * 100, "overlays": []})["image"] == "png"


@pytest.mark.asyncio
async def test_emit_tool_result_uses_compact_output():
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    await emit_tool_result("get_candles", [{"t": 1}], emit=emit, tool_id="", agent="FoxAgent")
    assert events[0][0] == "agent_tool_result"
    assert events[0][1]["name"] == "get_candles"
    assert events[0][1]["output"] == [{"t": 1}]
