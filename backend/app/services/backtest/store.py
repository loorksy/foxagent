"""Persist backtest reports (SQLite or in-memory fallback)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.schemas import new_id, utcnow
from app.services.backtest.models import BacktestReport, BacktestReportRow

_memory: dict[str, dict[str, Any]] = {}


def _row_public(row: BacktestReportRow | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    try:
        payload = json.loads(row.payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    payload.update(
        {
            "id": row.id,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "strategyId": row.strategy_id,
            "days": row.days,
            "totalTrades": row.total_trades,
            "winRate": row.win_rate,
            "totalR": row.total_r,
            "profitFactor": row.profit_factor,
            "maxDrawdownR": row.max_drawdown_r,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        }
    )
    return payload


async def save_report(report: BacktestReport) -> dict[str, Any]:
    report.id = report.id or new_id("bt")
    report.createdAt = report.createdAt or utcnow()
    payload = report.model_dump(mode="json")
    summary = {
        "id": report.id,
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "strategyId": report.strategyId,
        "days": report.days,
        "totalTrades": report.totalTrades,
        "winRate": report.winRate,
        "totalR": report.totalR,
        "profitFactor": report.profitFactor,
        "maxDrawdownR": report.maxDrawdownR,
        "createdAt": report.createdAt.isoformat() if report.createdAt else None,
        **payload,
    }
    if SessionLocal is None:
        _memory[report.id] = summary
        return summary
    async with SessionLocal() as session:
        await session.merge(
            BacktestReportRow(
                id=report.id,
                symbol=report.symbol,
                timeframe=report.timeframe,
                strategy_id=report.strategyId,
                days=report.days,
                total_trades=report.totalTrades,
                win_rate=report.winRate,
                total_r=report.totalR,
                profit_factor=report.profitFactor,
                max_drawdown_r=report.maxDrawdownR,
                payload=json.dumps(payload, default=str),
                created_at=report.createdAt,
            )
        )
        await session.commit()
    return summary


async def list_reports(limit: int = 20) -> list[dict[str, Any]]:
    if SessionLocal is None:
        rows = sorted(_memory.values(), key=lambda r: r.get("createdAt") or "", reverse=True)
        return rows[:limit]
    async with SessionLocal() as session:
        result = await session.execute(
            select(BacktestReportRow).order_by(BacktestReportRow.created_at.desc()).limit(limit)
        )
        return [_row_public(row) for row in result.scalars()]


async def get_report(report_id: str) -> dict[str, Any] | None:
    if SessionLocal is None:
        return _memory.get(report_id)
    async with SessionLocal() as session:
        row = await session.get(BacktestReportRow, report_id)
        return None if row is None else _row_public(row)


def reset_backtest_memory() -> None:
    _memory.clear()
