"""Gold-only (XAU_USD) signal desk — does not place broker orders."""

from __future__ import annotations

from app.services.trading_bot.coordinator import TradingBotCoordinator, get_coordinator

__all__ = ["TradingBotCoordinator", "get_coordinator"]
