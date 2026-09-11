"""Unified gold strategy contract. XAU_USD only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.backtest.rules import STRATEGY_RULES

BUILTIN_META = {
    "gold_liquidity_sniper": {"name": "قناص سيولة الذهب", "description": "كنس سيولة آسيا ثم ارتداد من FVG"},
    "gold_breakout": {"name": "كسر نطاق الذهب", "description": "كسر نطاق آسيا مع إعادة اختبار"},
    "gold_trend_follow": {"name": "تتبع اتجاه الذهب", "description": "الدخول مع اتجاه H4 عند FVG/OB"},
    "gold_reversal": {"name": "انعكاس الذهب", "description": "انعكاس عند مناطق عرض/طلب قوية"},
    "gold_scalp": {"name": "سكالبينج الذهب", "description": "صفقات سريعة مع وقف ضيق"},
}

BUILTIN_IDS = (
    "gold_liquidity_sniper",
    "gold_breakout",
    "gold_trend_follow",
    "gold_reversal",
    "gold_scalp",
)

VALIDATION_THRESHOLDS = {
    "min_win_rate": 0.55,
    "min_profit_factor": 1.5,
    "min_total_trades": 50,
    "max_drawdown_r": 15.0,
    "min_total_r": 10.0,
}

WAREHOUSE_TFS = ("M15", "H1", "H4", "D")
SESSIONS = ("asia", "london", "ny", "london_ny_overlap", "london_close")
TRIGGERS = ("liquidity_sweep", "range_break", "fvg", "bos", "ob_reject", "news_candle")
FLAG_TO_TRIGGER = {
    "asian_sweep": "liquidity_sweep",
    "breakout": "range_break",
    "fvg_exists": "fvg",
    "bos_confirmed": "bos",
    "reversal": "ob_reject",
}
TRIGGER_TO_FLAG = {v: k for k, v in FLAG_TO_TRIGGER.items()}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_sessions(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    aliases = {"asian": "asia", "london-ny": "london_ny_overlap", "overlap": "london_ny_overlap"}
    for item in raw or []:
        key = aliases.get(str(item).lower().replace(" ", "_"), str(item).lower().replace(" ", "_"))
        if key in SESSIONS and key not in out:
            out.append(key)
    return out or list(SESSIONS)


def dsl_from_flags(conds: dict[str, Any] | None, sessions: list[str] | None = None) -> dict[str, Any]:
    flags = conds or {}
    triggers = [FLAG_TO_TRIGGER[k] for k, on in flags.items() if on and k in FLAG_TO_TRIGGER]
    return {
        "sessions": sanitize_sessions(sessions),
        "triggers": triggers or ["fvg"],
        "conditions": dict(flags),
    }


def flags_from_dsl(dsl: dict[str, Any] | None) -> dict[str, Any]:
    body = dsl or {}
    flags = dict(body.get("conditions") or {})
    for trigger in body.get("triggers") or []:
        flag = TRIGGER_TO_FLAG.get(str(trigger))
        if flag:
            flags[flag] = True
    return flags


class StrategyRule(BaseModel):
    id: str
    name: str
    description: str = ""
    timeframes: list[str] = Field(default_factory=lambda: ["M15"])
    direction: Literal["buy", "sell", "both"] = "both"
    entry_conditions: dict[str, Any] = Field(default_factory=dict)
    sessions: list[str] = Field(default_factory=lambda: list(SESSIONS))
    dsl: dict[str, Any] = Field(default_factory=dict)
    kind: Literal["dsl", "python"] = "dsl"
    code: str = ""
    pinned: bool = False
    stop_rule: str = "swing ± ATR"
    tp1_r: float = 1.5
    tp2_r: float = 3.0
    max_holding_bars: int = 48
    source: Literal["builtin", "claude_proposed", "manual"] = "manual"
    created_by: str = "operator"
    status: Literal["draft", "validated", "active", "rejected", "archived", "experimenting"] = "draft"
    validation_report_id: str | None = None
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    validated_at: datetime | None = None

    @property
    def timeframe(self) -> list[str]:
        return self.timeframes


def sanitize_timeframes(raw: list[str] | None) -> list[str]:
    out = []
    for item in raw or []:
        tf = str(item).upper().replace("D1", "D")
        if tf in WAREHOUSE_TFS and tf not in out:
            out.append(tf)
    return out or ["M15"]


def builtin_rules() -> list[StrategyRule]:
    rules: list[StrategyRule] = []
    for sid in BUILTIN_IDS:
        card = STRATEGY_RULES[sid]
        meta = BUILTIN_META.get(sid) or {}
        rules.append(
            StrategyRule(
                id=sid,
                name=str(meta.get("name") or card.get("name") or sid),
                description=str(meta.get("description") or card.get("entry") or ""),
                timeframes=list(card.get("timeframes") or ["M15"]),
                direction="both",
                entry_conditions=dict(card.get("conditions") or {}),
                sessions=list(SESSIONS),
                dsl=dsl_from_flags(dict(card.get("conditions") or {}), list(SESSIONS)),
                pinned=True,
                stop_rule=str(card.get("stop") or "swing ± ATR"),
                tp1_r=float(card.get("tp1") or 1.5),
                tp2_r=float(card.get("tp2") or 3.0),
                max_holding_bars=int(card.get("max_holding_bars") or 48),
                source="builtin",
                created_by="system",
                status="active",
            )
        )
    return rules


def evaluate_thresholds(report: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    wr = float(getattr(report, "winRate", 0) or 0)
    pf = float(getattr(report, "profitFactor", 0) or 0)
    trades = int(getattr(report, "totalTrades", 0) or 0)
    dd = float(getattr(report, "maxDrawdownR", 0) or 0)
    total_r = float(getattr(report, "totalR", 0) or 0)
    if wr < VALIDATION_THRESHOLDS["min_win_rate"]:
        reasons.append(f"win_rate {wr:.2f} < {VALIDATION_THRESHOLDS['min_win_rate']}")
    if pf < VALIDATION_THRESHOLDS["min_profit_factor"]:
        reasons.append(f"profit_factor {pf:.2f} < {VALIDATION_THRESHOLDS['min_profit_factor']}")
    if trades < VALIDATION_THRESHOLDS["min_total_trades"]:
        reasons.append(f"trades {trades} < {VALIDATION_THRESHOLDS['min_total_trades']}")
    if dd > VALIDATION_THRESHOLDS["max_drawdown_r"]:
        reasons.append(f"drawdown {dd:.2f}R > {VALIDATION_THRESHOLDS['max_drawdown_r']}")
    if total_r < VALIDATION_THRESHOLDS["min_total_r"]:
        reasons.append(f"total_r {total_r:.2f} < {VALIDATION_THRESHOLDS['min_total_r']}")
    return not reasons, reasons
