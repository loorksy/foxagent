"""Backtest report models and SQLite row."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas import utcnow


class BacktestTrade(BaseModel):
    strategyId: str
    timeframe: str
    entryTime: datetime
    exitTime: datetime
    direction: Literal["buy", "sell"]
    entryPrice: float
    stopLoss: float
    takeProfit1: float
    takeProfit2: float
    exitPrice: float
    pnlR: float
    pnlPercent: float
    exitReason: Literal["stop_loss", "tp1", "tp2", "breakeven", "timeout"]


class BacktestReport(BaseModel):
    id: str = ""
    symbol: str = "XAU_USD"
    timeframe: str
    strategyId: str | None = None
    days: int
    candlesTested: int
    totalTrades: int
    wins: int
    losses: int
    winRate: float
    averageR: float
    totalR: float
    profitFactor: float
    maxDrawdownR: float
    trades: list[BacktestTrade] = Field(default_factory=list)
    byStrategy: dict[str, dict[str, Any]] = Field(default_factory=dict)
    bySession: dict[str, dict[str, Any]] = Field(default_factory=dict)
    byMonth: dict[str, dict[str, Any]] = Field(default_factory=dict)
    textReport: str = ""
    createdAt: datetime | None = None


class BacktestRunRequest(BaseModel):
    timeframe: str = "M15"
    strategyId: str | None = None
    days: int = 365
    riskPercent: float = 1.0
    minRr: float = 2.0


class BacktestReportRow(Base):
    __tablename__ = "backtest_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), default="XAU_USD")
    timeframe: Mapped[str] = mapped_column(String(16))
    strategy_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    days: Mapped[int] = mapped_column(Integer)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_r: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_r: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
