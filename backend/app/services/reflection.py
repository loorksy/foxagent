"""Post-trade reflection — TradingAgents Reflector.reflect_on_final_decision pattern."""

from __future__ import annotations

import logging
from typing import Any

from app.db import get_recommendation, list_recommendations
from app.services.memory_log import TERMINAL_STATUSES, pending_for_recommendation, update_with_outcome
from app.services.settings_store import resolve_anthropic_key

logger = logging.getLogger(__name__)

REFLECT_PROMPT = (
    "You are a trading analyst reviewing your own past decision now that the outcome is known.\n"
    "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
    "Cover in order:\n"
    "1. Was the directional call correct? (cite the pnl / R figure)\n"
    "2. Which part of the investment thesis held or failed?\n"
    "3. One concrete lesson to apply to the next similar analysis.\n"
)


def deterministic_lesson(decision: str, outcome: str, pnl: float) -> str:
    """Offline reflector used when Claude is unavailable — still a real outcome-conditioned lesson."""
    direction = "worked" if pnl > 0 else "failed"
    thesis = (decision or "the prior thesis").strip().replace("\n", " ")[:280]
    return (
        f"The {outcome} close {direction} with {pnl:+.2f}R. "
        f"Thesis under review: {thesis}. "
        f"Next similar scan should require the same liquidity condition to be mitigated before entry."
    )


async def write_reflection(recommendation_id: str, outcome: str, pnl: float) -> dict[str, Any] | None:
    pending = await pending_for_recommendation(recommendation_id)
    if pending is None:
        return None
    lesson = deterministic_lesson(pending.get("decision") or "", outcome, pnl)
    api_key = await resolve_anthropic_key()
    if api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=220,
                system=REFLECT_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Outcome: {outcome}\nPnL (R): {pnl:+.2f}\n\n"
                            f"Final Decision:\n{pending.get('decision') or ''}"
                        ),
                    }
                ],
            )
            text = "".join(getattr(b, "text", "") for b in msg.content).strip()
            if text:
                lesson = text
        except Exception as exc:
            logger.warning("Reflection LLM failed, using outcome-conditioned lesson: %s", exc)
    return await update_with_outcome(
        recommendation_id=recommendation_id,
        outcome=outcome,
        pnl=pnl,
        reflection=lesson,
    )


async def scan_closed_recommendations() -> int:
    recs = await list_recommendations(200)
    written = 0
    for rec in recs:
        status = str(rec.get("status") or "")
        if status not in TERMINAL_STATUSES:
            continue
        rec_id = rec.get("id")
        if not rec_id:
            continue
        if await pending_for_recommendation(rec_id) is None:
            continue
        pnl = float(rec.get("pnlPips") or 0.0)
        result = await write_reflection(rec_id, status, pnl)
        if result:
            written += 1
    return written
