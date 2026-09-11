from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.schemas import new_id, utcnow
from app.services.trading_bot.models import BotSignalRow, PatternMemoryRow, StrategyPerformanceRow

_memory_signals: dict[str, dict[str, Any]] = {}
_memory_patterns: dict[str, dict[str, Any]] = {}
_memory_perf: dict[str, dict[str, Any]] = {}


def _signal_dict(row: BotSignalRow | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    extra = {}
    try:
        extra = json.loads(row.extra_json or "{}")
    except Exception:
        extra = {}
    return {
        "id": row.id,
        "agentType": row.agent_type,
        "strategyId": row.strategy_id,
        "instrument": row.instrument,
        "timeframe": row.timeframe,
        "signalType": row.signal_type,
        "entryPrice": row.entry_price,
        "stopLoss": row.stop_loss,
        "takeProfit1": row.take_profit1,
        "takeProfit2": row.take_profit2,
        "confidence": row.confidence,
        "riskReward": row.risk_reward,
        "status": row.status,
        "economicEventId": row.economic_event_id,
        "pnl": row.pnl,
        "recommendationId": row.recommendation_id,
        "botId": str(extra.get("botId") or ""),
        "mode": str(extra.get("mode") or "signal"),
        "metadata": extra,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "closedAt": row.closed_at.isoformat() if row.closed_at else None,
    }


def signal_payload(
    *,
    agent_type: str,
    strategy_id: str,
    timeframe: str,
    signal_type: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    confidence: float,
    risk_reward: float,
    economic_event_id: str | None = None,
    extra: dict[str, Any] | None = None,
    signal_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": signal_id or new_id("sig"),
        "agentType": agent_type,
        "strategyId": strategy_id,
        "instrument": "XAU_USD",
        "timeframe": timeframe,
        "signalType": signal_type,
        "entryPrice": entry,
        "stopLoss": stop,
        "takeProfit1": tp1,
        "takeProfit2": tp2,
        "confidence": confidence,
        "riskReward": risk_reward,
        "status": "pending",
        "economicEventId": economic_event_id,
        "pnl": 0.0,
        "recommendationId": "",
        "metadata": extra or {},
        "createdAt": utcnow().isoformat(),
        "closedAt": None,
    }


async def save_signal(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("id", new_id("sig"))
    payload.setdefault("instrument", "XAU_USD")
    payload.setdefault("status", "pending")
    # botId/mode ride inside metadata so the SQL schema stays unchanged.
    metadata = dict(payload.get("metadata") or {})
    if payload.get("botId"):
        metadata.setdefault("botId", str(payload["botId"]))
    if payload.get("mode"):
        metadata.setdefault("mode", str(payload["mode"]))
    payload["metadata"] = metadata
    if SessionLocal is None:
        _memory_signals[payload["id"]] = payload
        return payload
    async with SessionLocal() as session:
        created = payload.get("createdAt")
        created_dt = utcnow()
        if isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created_dt = utcnow()
        row = BotSignalRow(
            id=payload["id"],
            agent_type=payload.get("agentType") or "",
            strategy_id=payload.get("strategyId") or "",
            instrument=payload.get("instrument") or "XAU_USD",
            timeframe=payload.get("timeframe") or "M15",
            signal_type=payload.get("signalType") or "buy",
            entry_price=float(payload.get("entryPrice") or 0),
            stop_loss=float(payload.get("stopLoss") or 0),
            take_profit1=float(payload.get("takeProfit1") or 0),
            take_profit2=float(payload.get("takeProfit2") or 0),
            confidence=float(payload.get("confidence") or 0),
            risk_reward=float(payload.get("riskReward") or 0),
            status=payload.get("status") or "pending",
            economic_event_id=payload.get("economicEventId"),
            pnl=float(payload.get("pnl") or 0),
            recommendation_id=payload.get("recommendationId") or "",
            extra_json=json.dumps(payload.get("metadata") or {}, default=str),
            created_at=created_dt,
        )
        await session.merge(row)
        await session.commit()
    return payload


async def list_signals(limit: int = 50) -> list[dict[str, Any]]:
    if SessionLocal is None:
        rows = sorted(_memory_signals.values(), key=lambda r: r.get("createdAt") or "", reverse=True)
        return rows[:limit]
    async with SessionLocal() as session:
        result = await session.execute(select(BotSignalRow).order_by(BotSignalRow.created_at.desc()).limit(limit))
        return [_signal_dict(row) for row in result.scalars()]


async def list_signals_for_bot(bot_id: str, limit: int = 50, *, include_untagged: bool = False) -> list[dict[str, Any]]:
    """Signals produced by one bot instance. include_untagged keeps the default
    desk bot's history from before botId tagging existed."""
    out: list[dict[str, Any]] = []
    for row in await list_signals(300):
        rid = str(row.get("botId") or (row.get("metadata") or {}).get("botId") or "")
        if rid == bot_id or (include_untagged and not rid):
            out.append(row)
        if len(out) >= limit:
            break
    return out


async def get_signal(signal_id: str) -> dict[str, Any] | None:
    if SessionLocal is None:
        return _memory_signals.get(signal_id)
    async with SessionLocal() as session:
        row = await session.get(BotSignalRow, signal_id)
        return None if row is None else _signal_dict(row)


async def update_signal(signal_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    current = await get_signal(signal_id)
    if current is None:
        return None
    current.update(patch)
    if current.get("status") in {"won", "lost", "expired"} and not current.get("closedAt"):
        current["closedAt"] = utcnow().isoformat()
    await save_signal(current)
    await apply_signal_outcome(current)
    return current


async def apply_signal_outcome(signal: dict[str, Any]) -> None:
    status = str(signal.get("status") or "")
    if status not in {"won", "lost"}:
        return
    try:
        from app.services.trading_bot.circuit import note_outcome

        await note_outcome(str(signal.get("strategyId") or ""), won=status == "won")
    except Exception:
        pass
    await bump_performance(
        strategy_id=str(signal.get("strategyId") or ""),
        agent_type=str(signal.get("agentType") or ""),
        won=status == "won",
        pnl=float(signal.get("pnl") or 0),
        rr=float(signal.get("riskReward") or 0),
    )
    pattern = (signal.get("metadata") or {}).get("pattern")
    if pattern:
        await bump_pattern(str(pattern), str(signal.get("timeframe") or "M15"), won=status == "won", rr=float(signal.get("riskReward") or 0))


async def bump_performance(*, strategy_id: str, agent_type: str, won: bool, pnl: float, rr: float) -> dict[str, Any]:
    key = f"{agent_type}:{strategy_id}"
    current = _memory_perf.get(key) or {
        "id": key,
        "strategyId": strategy_id,
        "agentType": agent_type,
        "totalSignals": 0,
        "wins": 0,
        "losses": 0,
        "winRate": 0.0,
        "averageWin": 0.0,
        "averageLoss": 0.0,
        "profitFactor": 0.0,
    }
    if SessionLocal is not None:
        async with SessionLocal() as session:
            row = await session.get(StrategyPerformanceRow, key)
            if row:
                current = {
                    "id": row.id,
                    "strategyId": row.strategy_id,
                    "agentType": row.agent_type,
                    "totalSignals": row.total_signals,
                    "wins": row.wins,
                    "losses": row.losses,
                    "winRate": row.win_rate,
                    "averageWin": row.average_win,
                    "averageLoss": row.average_loss,
                    "profitFactor": row.profit_factor,
                }
    current["totalSignals"] = int(current.get("totalSignals") or 0) + 1
    if won:
        current["wins"] = int(current.get("wins") or 0) + 1
        n = current["wins"]
        current["averageWin"] = ((float(current.get("averageWin") or 0) * (n - 1)) + max(pnl, 0.0)) / n
    else:
        current["losses"] = int(current.get("losses") or 0) + 1
        n = current["losses"]
        current["averageLoss"] = ((float(current.get("averageLoss") or 0) * (n - 1)) + min(pnl, 0.0)) / n
    total = current["wins"] + current["losses"]
    current["winRate"] = (current["wins"] / total) if total else 0.0
    avg_loss = abs(float(current.get("averageLoss") or 0))
    current["profitFactor"] = (float(current.get("averageWin") or 0) / avg_loss) if avg_loss else 0.0
    _memory_perf[key] = current
    if SessionLocal is not None:
        async with SessionLocal() as session:
            await session.merge(
                StrategyPerformanceRow(
                    id=key,
                    strategy_id=strategy_id,
                    agent_type=agent_type,
                    total_signals=current["totalSignals"],
                    wins=current["wins"],
                    losses=current["losses"],
                    win_rate=current["winRate"],
                    average_win=current["averageWin"],
                    average_loss=current["averageLoss"],
                    profit_factor=current["profitFactor"],
                    updated_at=utcnow(),
                )
            )
            await session.commit()
    return current


async def list_performance(agent: str | None = None) -> list[dict[str, Any]]:
    rows = list(_memory_perf.values())
    if SessionLocal is not None:
        async with SessionLocal() as session:
            result = await session.execute(select(StrategyPerformanceRow))
            rows = [
                {
                    "id": row.id,
                    "strategyId": row.strategy_id,
                    "agentType": row.agent_type,
                    "totalSignals": row.total_signals,
                    "wins": row.wins,
                    "losses": row.losses,
                    "winRate": row.win_rate,
                    "averageWin": row.average_win,
                    "averageLoss": row.average_loss,
                    "profitFactor": row.profit_factor,
                    "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in result.scalars()
            ]
    if agent:
        rows = [r for r in rows if r.get("agentType") == agent]
    return rows


async def bump_pattern(pattern: str, timeframe: str, *, won: bool, rr: float) -> dict[str, Any]:
    key = f"{pattern}:{timeframe}"
    current = _memory_patterns.get(key) or {
        "id": key,
        "patternType": pattern,
        "timeframe": timeframe,
        "occurrences": 0,
        "successful": 0,
        "winRate": 0.0,
        "avgRr": 0.0,
        "notes": "",
    }
    current["occurrences"] = int(current.get("occurrences") or 0) + 1
    if won:
        current["successful"] = int(current.get("successful") or 0) + 1
    occ = current["occurrences"]
    current["winRate"] = current["successful"] / occ if occ else 0.0
    current["avgRr"] = ((float(current.get("avgRr") or 0) * (occ - 1)) + rr) / occ
    _memory_patterns[key] = current
    if SessionLocal is not None:
        async with SessionLocal() as session:
            await session.merge(
                PatternMemoryRow(
                    id=key,
                    pattern_type=pattern,
                    timeframe=timeframe,
                    occurrences=current["occurrences"],
                    successful=current["successful"],
                    win_rate=current["winRate"],
                    avg_rr=current["avgRr"],
                    notes=current.get("notes") or "",
                    updated_at=utcnow(),
                )
            )
            await session.commit()
    return current


async def get_pattern(pattern: str, timeframe: str) -> dict[str, Any] | None:
    key = f"{pattern}:{timeframe}"
    if SessionLocal is None:
        return _memory_patterns.get(key)
    async with SessionLocal() as session:
        row = await session.get(PatternMemoryRow, key)
        if row is None:
            return _memory_patterns.get(key)
        return {
            "id": row.id,
            "patternType": row.pattern_type,
            "timeframe": row.timeframe,
            "occurrences": row.occurrences,
            "successful": row.successful,
            "winRate": row.win_rate,
            "avgRr": row.avg_rr,
            "notes": row.notes,
        }


def reset_bot_memory() -> None:
    _memory_signals.clear()
    _memory_patterns.clear()
    _memory_perf.clear()


async def reset_bot_store() -> None:
    reset_bot_memory()
    if SessionLocal is None:
        return
    async with SessionLocal() as session:
        await session.execute(delete(BotSignalRow))
        await session.execute(delete(PatternMemoryRow))
        await session.execute(delete(StrategyPerformanceRow))
        await session.commit()
