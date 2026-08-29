from __future__ import annotations

import pytest

from app.schemas import TradeRecommendation
from app.services.analysis import build_recommendation
from app.services.chart_capture import render_candles_png
from app.services.simulator import generate_candles
from app.services.telegram_service import (
    CAPTION_LIMIT,
    format_trade_alert_html,
    parse_chat_ids,
    reset_alert_dedupe,
    send_trade_alert,
    telegram_ready,
)


def _rec(rationale: str = "Liquidity sweep below Asian session low with FVG mitigation.") -> TradeRecommendation:
    candles = generate_candles("XAU_USD", "M15", 120)
    return build_recommendation("XAU_USD", "15m", candles, htf_bias="BULLISH", model="claude-sonnet-4-5", vision_notes=rationale)


def test_parse_chat_ids_mixed_separators():
    assert parse_chat_ids(" 111, @desk; -10022\n333 ") == ["111", "@desk", "-10022", "333"]
    assert parse_chat_ids("") == []
    assert parse_chat_ids(None) == []


def test_telegram_ready_requires_all_three():
    assert telegram_ready("tok", ["1"], True) is True
    assert telegram_ready("", ["1"], True) is False
    assert telegram_ready("tok", [], True) is False
    assert telegram_ready("tok", ["1"], False) is False


def test_alert_html_contains_contract_fields():
    rec = _rec()
    html = format_trade_alert_html(rec, caption=False)
    assert "FOXAGENT NEW TRADE SETUP" in html
    assert "#XAUUSD" in html
    assert "15m" in html
    assert rec.tradeSetup.action.value in html
    assert "Entry Price" in html
    assert "Stop Loss" in html
    assert "TP1" in html
    assert "Claude Sonnet 4.5" in html
    assert "<b>" in html


def test_caption_respects_telegram_limit():
    rec = _rec("A" * 4000)
    caption = format_trade_alert_html(rec, caption=True)
    assert len(caption) <= CAPTION_LIMIT
    assert caption.endswith("…") or "FOXAGENT" in caption


def test_html_escapes_rationale():
    rec = _rec("<script>alert(1)</script> & more")
    html = format_trade_alert_html(rec)
    assert "<script>" not in html
    assert "&amp;" in html or "&gt;" in html


@pytest.mark.asyncio
async def test_send_skips_when_disabled():
    rec = _rec()
    result = await send_trade_alert(rec, None, token="x", chat_ids=["1"], enabled=False)
    assert result["skipped"] is True
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_send_skips_when_missing_secrets():
    rec = _rec()
    result = await send_trade_alert(rec, None, token="", chat_ids=[], enabled=True)
    assert result["skipped"] is True


def test_snapshot_with_overlays_is_png():
    candles = generate_candles("EUR_USD", "M15", 160)
    rec = build_recommendation("EUR_USD", "15m", candles, htf_bias="BEARISH")
    png = render_candles_png(candles, "EUR/USD 15m", rec.klineOverlays)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 8000


def test_reset_dedupe():
    reset_alert_dedupe()
