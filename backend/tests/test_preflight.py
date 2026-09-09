from __future__ import annotations

import pytest

from app.services.preflight import run_preflight
from app.services.run_control import reset_for_tests, set_paused


async def _fresh_health(*_a, **_k):
    return {
        "symbol": "XAU_USD",
        "timeframes": {"M15": {"stale": False}, "H1": {"stale": False}},
    }


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.mark.asyncio
async def test_preflight_blocks_when_paused(monkeypatch):
    monkeypatch.setattr("app.services.gold_warehouse.timeframe_health", _fresh_health)
    await set_paused(True)
    report = await run_preflight()
    assert report["blocking"] is True
    assert report["ok"] is False
    pause = next(c for c in report["checks"] if c["id"] == "pause")
    assert pause["ok"] is False
    assert pause["blocking"] is True


@pytest.mark.asyncio
async def test_preflight_ok_when_live(monkeypatch):
    monkeypatch.setattr("app.services.gold_warehouse.timeframe_health", _fresh_health)
    await set_paused(False)
    report = await run_preflight()
    assert report["blocking"] is False
    assert report["ok"] is True


def test_start_refuses_when_paused_without_force(client, auth_header, monkeypatch):
    from app.services.run_control import set_paused as real_set

    async def paused_true() -> bool:
        return True

    monkeypatch.setattr("app.services.run_control.is_paused", paused_true)
    monkeypatch.setattr("app.api.routes.is_paused", paused_true)
    monkeypatch.setattr("app.services.gold_warehouse.timeframe_health", _fresh_health)

    blocked = client.post("/api/bot/start", headers=auth_header)
    assert blocked.status_code == 409
    detail = blocked.json().get("detail") or {}
    assert (detail.get("preflight") or {}).get("blocking") is True

    forced = client.post("/api/bot/start?force=true", headers=auth_header)
    assert forced.status_code == 200
    assert forced.json().get("paused") is True or forced.json().get("enabled") is True
    _ = real_set
