"""Intent routing: decide how much of the agent crew a chat message needs.

The heavy pipeline (technical + fundamental + internal debate + risk manager)
runs only when the trader actually asked for a trade call. Questions get a
direct answer, analysis requests get analyst briefs plus a concise summary.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

INTENT_CHAT = "chat"
INTENT_ANALYSIS = "analysis"
INTENT_RECOMMENDATION = "recommendation"
INTENT_STRATEGY = "strategy"
VALID_INTENTS = {INTENT_CHAT, INTENT_ANALYSIS, INTENT_RECOMMENDATION, INTENT_STRATEGY}

CLASSIFIER_MAX_TOKENS = 8

_GREETING_RE = re.compile(
    r"^\s*(مرحبا|مرحبًا|اهلا|أهلا|هلا|السلام|صباح|مساء|كيف حالك|من انت|من أنت|ما اسمك|شكرا|شكرًا|"
    r"hi|hello|hey|good (morning|evening)|who are you|what are you|thanks|thank you)\b",
    re.I,
)
_RECO_RE = re.compile(
    r"(توصي|صفقة|صفقه|ادخل|أدخل|دخول|اشتري|أشتري|نفذ|نفّذ|سكالب|اعطني (صفقة|توصية|سيتاب)|هل (اشتري|ابيع|أبيع)|"
    r"\bsetup\b|trade idea|entry|long|short|recommend|signal|should i (buy|sell)|give me a trade)",
    re.I,
)
_STRAT_RE = re.compile(
    r"(استراتيجي|باك\s*تست|اختبار خلفي|\bbacktest\b|\bstrategy\b|\bstrategies\b)",
    re.I,
)
_ANALYSIS_RE = re.compile(
    r"(حلل|حلّل|تحليل|اتجاه|الاتجاه|هيكل|سيولة|مناطق|دعم|مقاومة|أخبار|اخبار|تقويم|السوق|الذهب|السعر|شارت|شمعة|جلسة|مسح|امسح|"
    r"analy|trend|structure|bias|liquidity|\bfvg\b|order block|\bpoi\b|price|chart|candle|session|news|calendar|market|\bscan\b)",
    re.I,
)
MACRO_RE = re.compile(
    r"(أخبار|اخبار|تقويم|فائدة|الفيدرالي|تضخم|بيانات|اقتصاد|جلسة|"
    r"news|calendar|macro|fomc|\bcpi\b|\bnfp\b|\bgdp\b|rate|fed|fundamental|session|sentiment)",
    re.I,
)

CLASSIFIER_SYSTEM = (
    "You route trader messages on a gold trading desk. Reply with exactly one lowercase word:\n"
    "chat — greetings, small talk, questions about the assistant itself, or anything not about markets\n"
    "analysis — questions about market conditions: trend, structure, liquidity, price, news, calendar, sessions\n"
    "recommendation — the trader wants a trade call: a setup, signal, entry/exit levels, or asks whether to buy/sell\n"
    "strategy — creating, editing, listing, backtesting, or discussing saved trading strategies\n"
    "Messages may be Arabic or English. Reply with the single word only."
)


def heuristic_intent(message: str) -> str | None:
    """Return an intent only when a single category clearly matches."""
    text = (message or "").strip()
    if not text:
        return INTENT_CHAT
    if _GREETING_RE.search(text) and len(text) <= 80:
        return INTENT_CHAT
    hits = [
        intent
        for intent, rx in (
            (INTENT_RECOMMENDATION, _RECO_RE),
            (INTENT_STRATEGY, _STRAT_RE),
            (INTENT_ANALYSIS, _ANALYSIS_RE),
        )
        if rx.search(text)
    ]
    if hits == [INTENT_RECOMMENDATION]:
        return INTENT_RECOMMENDATION
    if hits == [INTENT_STRATEGY]:
        return INTENT_STRATEGY
    if hits == [INTENT_ANALYSIS]:
        return INTENT_ANALYSIS
    if not hits and len(text) <= 120:
        return INTENT_CHAT
    return None


def fallback_intent(message: str) -> str:
    text = (message or "").strip()
    if _RECO_RE.search(text):
        return INTENT_RECOMMENDATION
    if _STRAT_RE.search(text):
        return INTENT_STRATEGY
    if _ANALYSIS_RE.search(text):
        return INTENT_ANALYSIS
    return INTENT_CHAT


async def classify_intent(client: Any, model: str, message: str, history: str = "") -> str:
    """Heuristics for clear-cut messages, one tiny LLM call otherwise."""
    quick = heuristic_intent(message)
    if quick:
        return quick
    prompt = message.strip()
    if history:
        prompt = f"Recent conversation:\n{history[-1200:]}\n\nLatest trader message:\n{prompt}"
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=CLASSIFIER_MAX_TOKENS,
            system=CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        word = ""
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", "") == "text":
                word += block.text
        word = word.strip().lower().split()[0] if word.strip() else ""
        if word in VALID_INTENTS:
            return word
    except Exception as exc:
        logger.warning("intent classification failed, using heuristics: %s", exc)
    return fallback_intent(message)


def wants_macro(message: str) -> bool:
    return bool(MACRO_RE.search(message or ""))
