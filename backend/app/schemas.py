from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "rec") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Sentiment(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class RecommendationStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    IN_PROFIT = "IN_PROFIT"
    HIT_TP1 = "HIT_TP1"
    HIT_TP2 = "HIT_TP2"
    STOPPED_OUT = "STOPPED_OUT"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class OverlayPoint(BaseModel):
    timestamp: int
    value: float
    dataIndex: int | None = None


class OverlayStyles(BaseModel):
    fillColor: str | None = None
    borderColor: str | None = None
    lineColor: str | None = None
    lineWidth: int | None = None
    color: str | None = None
    textColor: str | None = None
    backgroundColor: str | None = None

    model_config = {"extra": "allow"}


class KlineOverlay(BaseModel):
    name: Literal[
        "trendLine",
        "rect",
        "fibonacci",
        "priceLine",
        "textAnnotation",
        "segment",
        "fibonacciLine",
        "simpleAnnotation",
        "horizontalStraightLine",
        "rayLine",
    ]
    groupId: str | None = None
    id: str | None = None
    points: list[OverlayPoint] = Field(default_factory=list)
    styles: OverlayStyles | dict[str, Any] = Field(default_factory=dict)
    annotationText: str | None = None
    extendData: Any = None
    lock: bool = True
    visible: bool = True
    zLevel: int = 0


class TakeProfitLevel(BaseModel):
    level: int
    price: float
    ratio: str


class TradeSetup(BaseModel):
    action: TradeAction
    orderType: OrderType = OrderType.LIMIT
    entryPrice: float
    stopLoss: float
    takeProfitLevels: list[TakeProfitLevel] = Field(default_factory=list)
    riskRewardRatio: float = 0.0

    @field_validator("riskRewardRatio", mode="before")
    @classmethod
    def coerce_rr(cls, v: Any) -> float:
        if v is None or v == "":
            return 0.0
        return float(v)


class TradeRecommendation(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rec"))
    timestamp: datetime = Field(default_factory=utcnow)
    symbol: str
    timeframe: str
    sentiment: Sentiment
    tradeSetup: TradeSetup
    rationale: str
    confluence: list[str] = Field(default_factory=list)
    klineOverlays: list[KlineOverlay] = Field(default_factory=list)
    status: RecommendationStatus = RecommendationStatus.PENDING
    pnlPips: float | None = None
    pnlPercent: float | None = None
    model: str | None = None
    visionNotes: str | None = None
    focusTimestamp: int | None = None

    model_config = {"extra": "allow"}


class OHLCV(BaseModel):
    time: datetime
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    complete: bool = True

    def to_kline(self) -> dict[str, float | int]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class CandleRequest(BaseModel):
    instrument: str = "XAU_USD"
    granularity: str = "M15"
    count: int = Field(default=300, ge=1, le=5000)
    from_time: datetime | None = None
    to_time: datetime | None = None


class ChatRequest(BaseModel):
    message: str
    symbol: str = "XAU_USD"
    timeframe: str = "15m"
    model: str = "claude-sonnet-4-5"
    sessionId: str | None = None


class SessionCreate(BaseModel):
    id: str | None = None
    symbol: str = "XAU_USD"
    timeframe: str = "15m"
    title: str = ""


class SessionUpdate(BaseModel):
    title: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    state: dict[str, Any] | None = None


class SettingsPayload(BaseModel):
    anthropicApiKey: str = ""
    oandaApiToken: str = ""
    oandaAccountId: str = ""
    oandaEnvironment: Literal["practice", "live"] = "practice"
    defaultClaudeModel: str = "claude-sonnet-4-5"
    maxRiskPercent: float = 1.0
    minRiskReward: float = 2.0
    allowedSessions: list[str] = Field(default_factory=lambda: ["london", "ny", "asian"])
    telegramBotToken: str = ""
    telegramChatId: str = ""
    enableTelegramNotifications: bool = False


class SettingsPublic(BaseModel):
    anthropicApiKeySet: bool = False
    oandaApiTokenSet: bool = False
    oandaAccountId: str = ""
    oandaEnvironment: str = "practice"
    defaultClaudeModel: str = "claude-sonnet-4-5"
    maxRiskPercent: float = 1.0
    minRiskReward: float = 2.0
    allowedSessions: list[str] = Field(default_factory=list)
    oandaConfigured: bool = False
    anthropicConfigured: bool = False
    dataMode: Literal["oanda", "simulator"] = "simulator"
    telegramBotTokenSet: bool = False
    telegramChatId: str = ""
    enableTelegramNotifications: bool = False
    telegramConfigured: bool = False


class WsEvent(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    runId: str | None = None
    ts: datetime = Field(default_factory=utcnow)


class LivePrice(BaseModel):
    instrument: str
    bid: float
    ask: float
    mid: float
    time: datetime
    spread: float = 0.0
    source: str = "simulator"
