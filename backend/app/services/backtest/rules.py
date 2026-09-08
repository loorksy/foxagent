"""Deterministic ICT rule cards for the five gold strategies. Warehouse TFs only."""

from __future__ import annotations

STRATEGY_RULES: dict[str, dict] = {
    "gold_liquidity_sniper": {
        "name": "قناص سيولة الذهب",
        "timeframes": ["M15"],
        "entry": "FVG midpoint after Asian sweep",
        "stop": "below sweep wick - 0.5*ATR",
        "tp1": 1.5,
        "tp2": 3.0,
        "max_holding_bars": 48,
        "conditions": {
            "asian_sweep": True,
            "fvg_exists": True,
            "bos_confirmed": True,
        },
    },
    "gold_breakout": {
        "name": "كسر نطاق الذهب",
        "timeframes": ["M15", "H1"],
        "entry": "breakout close + retest of Asian range",
        "stop": "other side of Asian range",
        "tp1": 1.5,
        "tp2": 3.0,
        "max_holding_bars": 24,
        "conditions": {},
    },
    "gold_trend_follow": {
        "name": "تتبع اتجاه الذهب",
        "timeframes": ["H1", "H4"],
        "entry": "H4 trend + H1 FVG/OB pullback",
        "stop": "beyond OB/FVG",
        "tp1": 1.5,
        "tp2": 3.0,
        "max_holding_bars": 120,
        "conditions": {},
    },
    "gold_reversal": {
        "name": "انعكاس الذهب",
        "timeframes": ["M15", "H1"],
        "entry": "rejection at supply/demand",
        "stop": "beyond rejection wick",
        "tp1": 1.5,
        "tp2": 3.0,
        "max_holding_bars": 36,
        "conditions": {},
    },
    "gold_scalp": {
        "name": "سكالبينج الذهب",
        "timeframes": ["M15"],
        "entry": "momentum close + FVG confluence",
        "stop": "0.5 * ATR",
        "tp1": 1.0,
        "tp2": 1.5,
        "max_holding_bars": 6,
        "conditions": {},
    },
}

WAREHOUSE_TFS = ("M15", "H1", "H4", "D")
BARS_PER_DAY = {"M15": 96, "H1": 24, "H4": 6, "D": 1}
GOLD_SYMBOL = "XAU_USD"
SLIPPAGE = 0.2
SPREAD_COST = 0.35
LOOKBACK = 120
