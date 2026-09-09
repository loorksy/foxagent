"""Deterministic ICT backtest on stored XAU_USD candles.

Reads gold_warehouse only. No Claude, no OANDA, no simulator, no broker orders.
Decision at bar i uses candles[..., i] exclusively. Fill is the next bar's open.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.schemas import OHLCV
from app.services.analysis import StructureReport, analyze_structure
from app.services.gold_warehouse import load_latest, warehouse_tf
from app.services.macro_feed import current_session
from app.services.trading_bot.multi_strategy_agent import (
    _aligned_fvg,
    _aligned_ob,
    atr,
    build_rule_signal,
    evaluate_rule,
)
from app.services.backtest.models import BacktestReport, BacktestTrade
from app.services.backtest.rules import (
    BARS_PER_DAY,
    GOLD_SYMBOL,
    LOOKBACK,
    SLIPPAGE,
    SPREAD_COST,
    STRATEGY_RULES,
    WAREHOUSE_TFS,
)


ExitReason = Literal["stop_loss", "tp1", "tp2", "breakeven", "timeout"]


def _aware(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def apply_slippage(side: str, price: float, slippage: float = SLIPPAGE) -> float:
    return price + slippage if side == "buy" else price - slippage


def r_targets(entry: float, stop: float, side: str, tp1_r: float, tp2_r: float) -> tuple[float, float, float]:
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(abs(entry) * 0.001, 0.05)
    if side == "buy":
        return entry + tp1_r * risk, entry + tp2_r * risk, risk
    return entry - tp1_r * risk, entry - tp2_r * risk, risk


def mark_r(side: str, entry: float, exit_price: float, risk: float) -> float:
    if risk <= 0:
        return 0.0
    if side == "buy":
        return (exit_price - entry) / risk
    return (entry - exit_price) / risk


def simulate_trade(
    *,
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    tp1_r: float,
    tp2_r: float,
    bars: list[OHLCV],
    max_holding_bars: int,
    spread: float = SPREAD_COST,
    apply_spread: bool = True,
) -> dict[str, Any]:
    """Walk future bars. SL is checked before TP1 on the same bar (no intra-bar optimism)."""
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(abs(entry) * 0.001, 0.05)
    remaining = 1.0
    realized = 0.0
    tp1_done = False
    be = False
    exit_price = entry
    reason: ExitReason = "timeout"
    held = 0
    path = bars[: max(1, max_holding_bars)]

    for bar in path:
        held += 1
        sl_level = entry if be else stop
        if side == "buy":
            hit_sl = bar.low <= sl_level
            hit_tp1 = bar.high >= tp1
            hit_tp2 = bar.high >= tp2
            hit_be = be and bar.low <= entry
        else:
            hit_sl = bar.high >= sl_level
            hit_tp1 = bar.low <= tp1
            hit_tp2 = bar.low <= tp2
            hit_be = be and bar.high >= entry

        if not be and hit_sl:
            realized += -1.0 * remaining
            remaining = 0.0
            exit_price = sl_level
            reason = "stop_loss"
            break

        if not tp1_done and hit_tp1:
            realized += tp1_r * 0.5
            remaining = 0.5
            tp1_done = True
            be = True
            exit_price = tp1
            reason = "tp1"
            if hit_tp2:
                realized += tp2_r * remaining
                remaining = 0.0
                exit_price = tp2
                reason = "tp2"
                break
            if (side == "buy" and bar.low <= entry) or (side == "sell" and bar.high >= entry):
                remaining = 0.0
                exit_price = entry
                reason = "breakeven"
                break
            continue

        if tp1_done and hit_tp2:
            realized += tp2_r * remaining
            remaining = 0.0
            exit_price = tp2
            reason = "tp2"
            break

        if tp1_done and hit_be:
            remaining = 0.0
            exit_price = entry
            reason = "breakeven"
            break

        exit_price = bar.close

    if remaining > 0:
        realized += mark_r(side, entry, exit_price, risk) * remaining
        reason = "timeout" if reason not in {"tp1"} else reason
        if not tp1_done:
            reason = "timeout"

    if apply_spread:
        realized -= spread / risk
    last = path[held - 1] if path else None
    return {
        "exitPrice": round(exit_price, 3),
        "pnlR": round(realized, 4),
        "exitReason": reason,
        "barsHeld": held,
        "exitTime": last.time if last else None,
        "risk": risk,
    }


def strategy_stop(strategy_id: str, candles: list[OHLCV], report: StructureReport, side: str, fill: float, stop_rule: str = "") -> float:
    range_atr = atr(candles)
    last = candles[-1]
    text = f"{strategy_id} {stop_rule}".lower()
    if strategy_id == "gold_liquidity_sniper" or "sweep" in text:
        return last.low - 0.5 * range_atr if side == "buy" else last.high + 0.5 * range_atr
    if strategy_id == "gold_breakout" or "asian range" in text:
        return report.asian_low if side == "buy" else report.asian_high
    if strategy_id == "gold_trend_follow" or "ob" in text or "fvg" in text:
        zone = _aligned_fvg(report, side) or _aligned_ob(report, side)
        if zone:
            return zone.low - 0.15 * range_atr if side == "buy" else zone.high + 0.15 * range_atr
        return last.low - 0.5 * range_atr if side == "buy" else last.high + 0.5 * range_atr
    if strategy_id == "gold_reversal" or "wick" in text or "rejection" in text:
        return last.low - 0.1 * range_atr if side == "buy" else last.high + 0.1 * range_atr
    if strategy_id == "gold_scalp" or "0.5" in text:
        return fill - 0.5 * range_atr if side == "buy" else fill + 0.5 * range_atr
    return fill - 0.5 * range_atr if side == "buy" else fill + 0.5 * range_atr


def conditions_ok(conds: dict[str, Any] | None, report: StructureReport) -> bool:
    from app.services.trading_bot.strategy_schema import flags_from_dsl

    flags = dict(conds or {})
    if flags.get("triggers") or flags.get("conditions"):
        flags = flags_from_dsl(flags)
    if flags.get("asian_sweep") and not report.liquidity_sweep:
        return False
    if flags.get("fvg_exists") and not report.fvgs:
        return False
    if flags.get("bos_confirmed") and not report.last_bos:
        return False
    return True


def empty_bucket() -> dict[str, Any]:
    return {"trades": 0, "wins": 0, "losses": 0, "winRate": 0.0, "totalR": 0.0, "averageR": 0.0}


def rollup(trades: list[BacktestTrade]) -> dict[str, Any]:
    bucket = empty_bucket()
    if not trades:
        return bucket
    bucket["trades"] = len(trades)
    bucket["wins"] = sum(1 for t in trades if t.pnlR > 0)
    bucket["losses"] = sum(1 for t in trades if t.pnlR <= 0)
    bucket["totalR"] = round(sum(t.pnlR for t in trades), 4)
    bucket["averageR"] = round(bucket["totalR"] / len(trades), 4)
    bucket["winRate"] = round(bucket["wins"] / len(trades), 4)
    return bucket


def max_drawdown_r(trades: list[BacktestTrade]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in trades:
        equity += trade.pnlR
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(abs(max_dd), 4)


def profit_factor(trades: list[BacktestTrade]) -> float:
    gains = sum(t.pnlR for t in trades if t.pnlR > 0)
    losses = abs(sum(t.pnlR for t in trades if t.pnlR < 0))
    if losses <= 0:
        return 0.0 if gains <= 0 else float(gains)
    return round(gains / losses, 4)


async def _resolve_rules(timeframe: str, strategy_id: str | None, extra: Any | None):
    from app.services.trading_bot.strategy_library import get_library
    from app.services.trading_bot.strategy_schema import builtin_rules

    if extra is not None and timeframe in getattr(extra, "timeframes", []):
        if strategy_id is None or extra.id == strategy_id:
            return [extra]
    try:
        lib = get_library()
        if strategy_id:
            rule = await lib.get(strategy_id)
            return [rule] if rule and timeframe in rule.timeframes else []
        return await lib.list_runnable(timeframe)
    except Exception:
        fallback = builtin_rules()
        if strategy_id:
            return [r for r in fallback if r.id == strategy_id and timeframe in r.timeframes]
        return [r for r in fallback if timeframe in r.timeframes]


async def load_warehouse_window(timeframe: str, days: int, lookback: int = LOOKBACK) -> list[OHLCV]:
    tf = warehouse_tf(timeframe)
    if tf is None:
        return []
    count = int(days) * BARS_PER_DAY.get(tf, 96) + lookback
    return await load_latest(tf, max(count, lookback + 20))


class BacktestEngine:
    """محرك باك تست حتمي لقواعد ICT على شموع الذهب المخزّنة."""

    def __init__(self, symbol: str = GOLD_SYMBOL):
        self.symbol = symbol
        self.strategies = STRATEGY_RULES

    async def run(
        self,
        timeframe: str,
        strategy_id: str | None = None,
        days: int = 365,
        risk_percent: float = 1.0,
        min_rr: float = 2.0,
        candles: list[OHLCV] | None = None,
        persist: bool = False,
        rule: Any | None = None,
    ) -> BacktestReport:
        tf = warehouse_tf(timeframe) or timeframe.upper()
        if tf not in WAREHOUSE_TFS:
            raise ValueError(f"Backtest supports {WAREHOUSE_TFS} only")
        series = list(candles) if candles is not None else await load_warehouse_window(tf, days)
        series.sort(key=lambda c: c.timestamp)
        wanted_rules = await _resolve_rules(tf, strategy_id, rule)
        wanted = [r.id for r in wanted_rules]
        trades: list[BacktestTrade] = []
        busy_until: dict[str, int] = {}
        start = min(LOOKBACK, max(20, len(series) // 4))
        for i in range(start, max(start, len(series) - 1)):
            window = series[max(0, i - LOOKBACK + 1) : i + 1]
            if len(window) < 20:
                continue
            report = analyze_structure(window)
            for item in wanted_rules:
                sid = item.id
                if i <= busy_until.get(sid, -1):
                    continue
                if not evaluate_rule(item, window, report) or not conditions_ok(item.entry_conditions, report):
                    continue
                built = build_rule_signal(item, window, report, tf)
                if not built:
                    continue
                side = built["signalType"]
                nxt = series[i + 1]
                fill = apply_slippage(side, nxt.open)
                stop = strategy_stop(sid, window, report, side, fill, item.stop_rule)
                if side == "buy" and stop >= fill:
                    stop = fill - max(atr(window) * 0.35, 0.2)
                if side == "sell" and stop <= fill:
                    stop = fill + max(atr(window) * 0.35, 0.2)
                tp1_r = float(item.tp1_r)
                tp2_r = float(item.tp2_r)
                if tp2_r + 1e-9 < min_rr:
                    continue
                tp1, tp2, risk = r_targets(fill, stop, side, tp1_r, tp2_r)
                if risk / max(abs(fill), 1.0) * 100.0 > max(risk_percent, 0.05) * 20:
                    if abs(fill - stop) / max(abs(fill), 1.0) > 0.05:
                        continue
                path = series[i + 1 : i + 1 + int(item.max_holding_bars)]
                if not path:
                    continue
                sim = simulate_trade(
                    side=side,
                    entry=fill,
                    stop=stop,
                    tp1=tp1,
                    tp2=tp2,
                    tp1_r=tp1_r,
                    tp2_r=tp2_r,
                    bars=path,
                    max_holding_bars=int(item.max_holding_bars),
                )
                exit_time = sim["exitTime"] or path[-1].time
                trade = BacktestTrade(
                    strategyId=sid,
                    timeframe=tf,
                    entryTime=_aware(nxt.time),
                    exitTime=_aware(exit_time),
                    direction=side,  # type: ignore[arg-type]
                    entryPrice=round(fill, 3),
                    stopLoss=round(stop, 3),
                    takeProfit1=round(tp1, 3),
                    takeProfit2=round(tp2, 3),
                    exitPrice=sim["exitPrice"],
                    pnlR=sim["pnlR"],
                    pnlPercent=round(sim["pnlR"] * risk_percent, 4),
                    exitReason=sim["exitReason"],
                )
                trades.append(trade)
                busy_until[sid] = i + int(sim["barsHeld"])

        wins = sum(1 for t in trades if t.pnlR > 0)
        losses = sum(1 for t in trades if t.pnlR <= 0)
        total_r = round(sum(t.pnlR for t in trades), 4)
        report_out = BacktestReport(
            symbol=self.symbol,
            timeframe=tf,
            strategyId=strategy_id,
            days=days,
            candlesTested=len(series),
            totalTrades=len(trades),
            wins=wins,
            losses=losses,
            winRate=round(wins / len(trades), 4) if trades else 0.0,
            averageR=round(total_r / len(trades), 4) if trades else 0.0,
            totalR=total_r,
            profitFactor=profit_factor(trades),
            maxDrawdownR=max_drawdown_r(trades),
            trades=trades,
            byStrategy={sid: rollup([t for t in trades if t.strategyId == sid]) for sid in wanted},
            bySession=_group_session(trades),
            byMonth=_group_month(trades),
        )
        from app.services.backtest.report_writer import generate_text_report

        report_out.textReport = generate_text_report(report_out)
        if persist:
            from app.services.backtest.store import save_report

            saved = await save_report(report_out)
            report_out.id = saved.get("id") or report_out.id
        return report_out


def _group_session(trades: list[BacktestTrade]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[BacktestTrade]] = {}
    for trade in trades:
        name = str(current_session(trade.entryTime).get("session") or "unknown")
        buckets.setdefault(name, []).append(trade)
    return {k: rollup(v) for k, v in buckets.items()}


def _group_month(trades: list[BacktestTrade]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[BacktestTrade]] = {}
    for trade in trades:
        key = _aware(trade.entryTime).strftime("%Y-%m")
        buckets.setdefault(key, []).append(trade)
    return {k: rollup(v) for k, v in buckets.items()}
