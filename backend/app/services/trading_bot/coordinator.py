"""Central gold-bot loop. Pause and botEnabled both freeze scanning."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from app.services.macro_feed import current_session
from app.services.risk_rules import RiskRejected, enforce_risk_gate, implied_risk_percent, _session_allowed
from app.services.trading_bot.multi_strategy_agent import MultiStrategyAgent
from app.services.trading_bot.news_candle_agent import NewsCandleAgent
from app.services.trading_bot.pattern_notes_agent import PatternNotesAgent
from app.services.trading_bot.promote import signal_to_recommendation
from app.services.trading_bot.store import list_signals, save_signal

logger = logging.getLogger(__name__)

_COORDINATOR: "TradingBotCoordinator | None" = None


class TradingBotCoordinator:
    def __init__(self) -> None:
        self.multi_strategy_agent = MultiStrategyAgent()
        self.pattern_notes_agent = PatternNotesAgent()
        self.news_candle_agent = NewsCandleAgent()
        self.is_running = False
        self.monitor_task: asyncio.Task | None = None
        self.started_at: float | None = None
        self.last_error = ""
        self.cycles = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self.is_running,
            "startedAt": self.started_at,
            "uptimeSeconds": (time.time() - self.started_at) if self.started_at else 0,
            "cycles": self.cycles,
            "lastError": self.last_error,
        }

    async def _settings(self):
        from app.services.settings_store import load_runtime_settings

        return await load_runtime_settings()

    async def start(self) -> dict[str, Any]:
        if os.environ.get("FOXAGENT_BOT_AUTOSTART", "1").strip().lower() in {"0", "false", "off"} and not self.is_running:
            # Tests may still call start() explicitly; only the lifespan honors this flag.
            pass
        if self.is_running:
            return self.snapshot()
        self.is_running = True
        self.started_at = time.time()
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Gold trading bot monitor started")
        return self.snapshot()

    async def stop(self) -> dict[str, Any]:
        self.is_running = False
        task = self.monitor_task
        self.monitor_task = None
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self.started_at = None
        logger.info("Gold trading bot monitor stopped")
        return self.snapshot()

    async def on_pause_changed(self, paused: bool) -> None:
        from app.services.settings_store import load_runtime_settings

        if paused:
            if self.is_running:
                await self.stop()
            return
        runtime = await load_runtime_settings()
        if getattr(runtime, "botEnabled", False):
            await self.start()

    async def _monitor_loop(self) -> None:
        while self.is_running:
            try:
                from app.services.run_control import is_paused

                runtime = await self._settings()
                if await is_paused() or not getattr(runtime, "botEnabled", False):
                    await asyncio.sleep(max(5, int(getattr(runtime, "botScanInterval", 60) or 60)))
                    continue
                await self.run_cycle(runtime)
                self.cycles += 1
                await asyncio.sleep(max(5, int(getattr(runtime, "botScanInterval", 60) or 60)))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)[:240]
                logger.error("Monitor loop error: %s", exc)
                await asyncio.sleep(30)

    async def run_cycle(self, runtime: Any | None = None) -> list[dict[str, Any]]:
        runtime = runtime or await self._settings()
        agents = set(getattr(runtime, "botAgents", None) or ["multi_strategy", "pattern_notes", "news_candle"])
        active = list(getattr(runtime, "botActiveStrategies", None) or [])
        saved: list[dict[str, Any]] = []
        if "news_candle" in agents:
            for signal in await self.news_candle_agent.monitor_events():
                kept = await self._accept(signal, runtime)
                if kept:
                    saved.append(kept)
        if "multi_strategy" in agents:
            self.multi_strategy_agent.active = active or list(self.multi_strategy_agent.active)
            for signal in await self.multi_strategy_agent.scan_xau_usd():
                kept = await self._accept(signal, runtime)
                if kept:
                    saved.append(kept)
        if "pattern_notes" in agents:
            for signal in await self.pattern_notes_agent.detect_patterns():
                kept = await self._accept(signal, runtime)
                if kept:
                    saved.append(kept)
        return saved

    async def _bot_limits(self, signal: dict[str, Any], runtime: Any) -> bool:
        """Extra bot caps — may only tighten the sacred risk gate, never loosen it."""
        rr = float(signal.get("riskReward") or 0)
        if rr < float(getattr(runtime, "botMinRr", 2.0) or 2.0):
            return False
        risk_pct = implied_risk_percent(float(signal.get("entryPrice") or 0), float(signal.get("stopLoss") or 0))
        if risk_pct > float(getattr(runtime, "botMaxRiskPercent", 1.0) or 1.0):
            return False
        allowed = list(getattr(runtime, "botAllowedSessions", None) or [])
        if allowed:
            session = current_session()
            if not _session_allowed(str(session.get("session") or ""), allowed):
                return False
        return True

    async def _accept(self, signal: dict[str, Any], runtime: Any | None = None) -> dict[str, Any] | None:
        runtime = runtime or await self._settings()
        rec = signal_to_recommendation(signal)
        try:
            await enforce_risk_gate(rec.model_dump(mode="json"))
        except RiskRejected as exc:
            logger.info("Bot signal rejected by risk gate: %s", exc)
            return None
        if not await self._bot_limits(signal, runtime):
            logger.info("Bot signal rejected by bot risk limits")
            return None
        stored = await save_signal(signal)
        try:
            from app.services.telegram_service import schedule_bot_signal

            schedule_bot_signal(stored)
        except Exception:
            logger.debug("Bot telegram hook skipped")
        return stored


def get_coordinator() -> TradingBotCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = TradingBotCoordinator()
    return _COORDINATOR


def reset_coordinator() -> TradingBotCoordinator:
    global _COORDINATOR
    _COORDINATOR = TradingBotCoordinator()
    return _COORDINATOR


async def today_signal_count() -> int:
    rows = await list_signals(200)
    return len(rows)
