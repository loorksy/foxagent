from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.services import long_term_memory as mem
from app.services.mcp_tools import dispatch_tool


@pytest.mark.asyncio
async def test_capture_recall_and_drill_down(monkeypatch):
    monkeypatch.setattr("app.db.SessionLocal", None)
    mem._fallback.clear()
    persona = await mem.capture_memory(
        text="Desk prefers limit entries at the London sweep.",
        layer="L3",
        kind="persona",
        symbol="XAU_USD",
    )
    atom = await mem.capture_memory(
        text="Do not fade an unmitigated M15 FVG.",
        layer="L1",
        kind="constraint",
        symbol="XAU_USD",
        parent_id=persona["id"],
    )
    hits = await mem.search_memory("unmitigated FVG", symbol="XAU_USD", layers=("L1", "L2", "L3"))
    assert hits[0]["id"] == atom["id"]
    chain = await mem.drill_down(atom["id"])
    assert [row["id"] for row in chain] == [atom["id"], persona["id"]]
    prompt = await mem.recall_for_prompt("XAU_USD", "FVG")
    assert "L1" in prompt
    assert "L3" in prompt
    assert "memory_recall" in prompt


@pytest.mark.asyncio
async def test_memory_survives_a_new_database_session(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'fox.db'}"
    engine = create_async_engine(url)
    first = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr("app.db.SessionLocal", first)
    saved = await mem.capture_memory(
        text="Remember the Asia range before London.",
        layer="L2",
        kind="scenario",
        symbol="XAU_USD",
    )
    await engine.dispose()

    engine2 = create_async_engine(url)
    second = async_sessionmaker(engine2, expire_on_commit=False)
    monkeypatch.setattr("app.db.SessionLocal", second)
    listed = await mem.list_long_term("XAU_USD")
    assert any(row["id"] == saved["id"] and "Asia range" in row["text"] for row in listed)
    await engine2.dispose()


@pytest.mark.asyncio
async def test_remember_phrase_promotes_an_atom(monkeypatch):
    monkeypatch.setattr("app.db.SessionLocal", None)
    mem._fallback.clear()
    await mem.record_turn(
        session_id="sess_1",
        symbol="XAU_USD",
        user_text="تذكر: لا تدخل قبل دقيقة من الخبر",
        assistant_text="تم.",
    )
    rows = await mem.list_long_term("XAU_USD")
    layers = {row["layer"] for row in rows}
    assert "L0" in layers
    assert "L1" in layers
    atom = next(row for row in rows if row["layer"] == "L1")
    assert atom["parentId"]


@pytest.mark.asyncio
async def test_agent_can_query_saved_memory(monkeypatch):
    monkeypatch.setattr("app.db.SessionLocal", None)
    mem._fallback.clear()
    saved = await dispatch_tool(
        "memory_capture",
        {"text": "Risk cap stays at 1 percent.", "layer": "L1", "kind": "constraint", "instrument": "XAU_USD"},
    )
    assert saved["ok"] is True
    found = await dispatch_tool(
        "memory_recall",
        {"memory_id": saved["memory"]["id"], "instrument": "XAU_USD"},
    )
    assert found["ok"] is True
    assert found["chain"][0]["text"] == "Risk cap stays at 1 percent."
    empty = await dispatch_tool("memory_capture", {"text": "   "})
    assert empty["ok"] is False
