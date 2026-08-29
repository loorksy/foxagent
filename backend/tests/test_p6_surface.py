from __future__ import annotations

from pathlib import Path

import pytest

from app.services.memory_log import decision_summary, list_entries, store_decision

ROOT = Path(__file__).resolve().parents[2]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def _exists(*parts: str) -> bool:
    return ROOT.joinpath(*parts).exists()


def test_removed_orphan_http_routes_are_gone(client, auth_header):
    gone = [
        ("POST", "/api/candles"),
        ("GET", "/api/price"),
        ("GET", "/api/chart-snapshot"),
        ("GET", "/api/recommendations/rec_missing"),
        ("POST", "/api/recommendations"),
    ]
    paths = client.app.openapi()["paths"]
    assert "/api/candles" in paths and "post" not in paths["/api/candles"]
    assert "/api/price" not in paths
    assert "/api/chart-snapshot" not in paths
    assert "/api/recommendations/{rec_id}" in paths
    assert "get" not in paths["/api/recommendations/{rec_id}"]
    assert "post" not in paths.get("/api/recommendations", {})
    for method, path in gone:
        resp = client.request(method, path, json={}, headers=auth_header)
        assert resp.status_code == 405 or resp.status_code == 404, f"{method} {path} still reachable: {resp.status_code}"


def test_ws_agent_endpoint_removed(client, auth_header):
    assert "/ws/agent" not in {getattr(r, "path", "") for r in client.app.router.routes}
    source = _read("backend", "app", "api", "ws.py")
    assert '/ws/agent"' not in source
    assert "agent_hub" not in source


def test_instruments_models_structure_memory_work(client, auth_header, monkeypatch):
    async def fake_probe(*_a, **_k):
        return {"ok": True, "keyValid": True, "detail": "ok"}

    monkeypatch.setattr("app.api.routes.probe_anthropic", fake_probe)

    instruments = client.get("/api/instruments", headers=auth_header)
    assert instruments.status_code == 200
    tickers = {row["ticker"] for row in instruments.json()["instruments"]}
    assert "XAU_USD" in tickers

    models = client.get("/api/models", headers=auth_header)
    assert models.status_code == 200
    ids = {row["id"] for row in models.json()["models"]}
    assert "claude-sonnet-4-5" in ids

    structure = client.get("/api/structure?instrument=XAU_USD&granularity=M15&count=80", headers=auth_header)
    assert structure.status_code == 200
    body = structure.json()
    assert "bias" in body
    assert "fvgCount" in body

    memory = client.get("/api/memory", headers=auth_header)
    assert memory.status_code == 200
    assert "entries" in memory.json()

    context = client.get("/api/memory/context?symbol=XAU_USD", headers=auth_header)
    assert context.status_code == 200
    assert context.json()["symbol"] == "XAU_USD"


@pytest.mark.asyncio
async def test_memory_list_returns_reference_not_full_payload(monkeypatch):
    monkeypatch.setattr("app.services.memory_log.SessionLocal", None)
    await store_decision(
        entry_id="mem_p6",
        symbol="XAU_USD",
        kind="risk",
        decision=decision_summary(recommendation_id="rec_p6", symbol="XAU_USD", action="BUY", rating="BULLISH"),
        rating="BULLISH",
        recommendation_id="rec_p6",
    )
    rows = await list_entries(include_pending=True)
    hit = next((row for row in rows if row["id"] == "mem_p6"), None)
    assert hit is not None
    assert "rec_p6" in hit["decision"]
    assert "entryPrice" not in hit["decision"]
    assert "{" not in hit["decision"]


def test_chart_nonce_is_wired_into_chart_canvas():
    source = _read("frontend", "src", "components", "ChartCanvas.tsx")
    assert "chartNonce" in source
    assert "period.granularity, chartNonce" in source or "chartNonce]" in source


def test_scan_and_setup_are_special_cased():
    source = _read("frontend", "src", "lib", "agentSend.ts")
    assert 'cmd === "scan"' in source
    assert "api.structure" in source
    assert 'cmd === "setup"' in source
    assert "SETUP_PROMPT" in source
    assert "api.streamChat" in source


def test_frontend_calls_models_instruments_memory():
    api = _read("frontend", "src", "lib", "api.ts")
    assert "/api/models" in api
    assert "/api/instruments" in api
    assert "/api/memory" in api
    assert "/api/structure" in api
    catalog = _read("frontend", "src", "stores", "catalog.ts")
    assert "api.models()" in catalog
    assert "api.instruments()" in catalog
    memory = _read("frontend", "src", "components", "memory", "MemoryPage.tsx")
    assert ".memory(" in memory or "api.memory(" in memory
    assert ".memoryContext(" in memory or "api.memoryContext(" in memory
    settings = _read("frontend", "src", "components", "settings", "SettingsPanel.tsx")
    assert "useCatalog" in settings
    composer = _read("frontend", "src", "components", "chat", "ChatComposer.tsx")
    assert "useCatalog" in composer


def test_dead_components_and_phase_types_are_gone():
    assert not _exists("frontend", "src", "components", "Workstation.tsx")
    types = _read("frontend", "src", "lib", "types.ts")
    assert "export type AgentPhase" not in types
    i18n = _read("frontend", "src", "i18n", "index.ts")
    assert "phaseNameKey" not in i18n
    en = _read("frontend", "src", "i18n", "messages", "en.ts")
    ar = _read("frontend", "src", "i18n", "messages", "ar.ts")
    assert "phase.1.name" not in en
    assert "phase.1.name" not in ar
    schemas = _read("backend", "app", "schemas.py")
    assert "class AgentPhase" not in schemas
