"""Multiple bot instances on one gold desk. Pause supremacy is sacred.

Types:
- strategy / quant: signals go risk gate -> save -> inbox approval -> telegram.
- alerts: notification-only signals (mode="alert"), never enter the approval queue.
- execution: like strategy, plus MT5 market orders through metaapi.place_market_order
  (the ONLY permitted broker path) — at approval time, or immediately when
  autoExecute is on. Requires a connected MT5 account to create/enable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.db import SessionLocal, kv_get, kv_set
from app.schemas import new_id, utcnow
from app.services.trading_bot.models import BotInstanceRow

logger = logging.getLogger(__name__)

AGENT_KINDS = ("multi_strategy", "pattern_notes", "news_candle")
BOT_TYPES = ("strategy", "quant", "alerts", "execution")
DEFAULT_BOT_ID = "bot-gold-default"
DEFAULT_BOT_NAME = "بوت الذهب"
SEED_KEY = "bot_instances_seeded"
MT5_GOLD_SYMBOL = "XAUUSD"

_memory_instances: dict[str, dict[str, Any]] = {}
_MANAGER: "BotManager | None" = None


class ExecutionNotAllowed(Exception):
    """Raised when an execution bot is created/enabled without a live MT5 link."""


class BotInstanceStats(BaseModel):
    cycles: int = 0
    lastError: str = ""
    lastSignalAt: str | None = None


class BotInstance(BaseModel):
    id: str = Field(default_factory=lambda: new_id("bot"))
    name: str
    type: Literal["strategy", "quant", "alerts", "execution"] = "strategy"
    enabled: bool = False
    scanIntervalSeconds: int = 60
    agents: list[str] = Field(default_factory=lambda: list(AGENT_KINDS))
    strategyIds: list[str] = Field(default_factory=list)
    minRr: float = 2.0
    maxRiskPercent: float = 1.0
    allowedSessions: list[str] = Field(default_factory=lambda: ["london", "ny", "asian"])
    autoExecute: bool = False
    orderVolume: float = 0.01
    createdAt: str = Field(default_factory=lambda: utcnow().isoformat())
    stats: BotInstanceStats = Field(default_factory=BotInstanceStats)


def instance_from_payload(body: dict[str, Any]) -> BotInstance:
    """Build a validated instance from an API payload. Raises ValueError with Arabic detail."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValueError("اسم البوت مطلوب")
    btype = str(body.get("type") or "strategy")
    if btype not in BOT_TYPES:
        raise ValueError("نوع البوت غير معروف")
    agents = [a for a in (body.get("agents") or []) if a in AGENT_KINDS]
    if not agents:
        agents = list(AGENT_KINDS) if btype in {"strategy", "alerts"} else ["multi_strategy"]
    return BotInstance(
        id=str(body.get("id") or new_id("bot")),
        name=name,
        type=btype,  # type: ignore[arg-type]
        enabled=bool(body.get("enabled") or False),
        scanIntervalSeconds=max(5, int(body.get("scanIntervalSeconds") or 60)),
        agents=agents,
        strategyIds=[str(s) for s in (body.get("strategyIds") or [])],
        minRr=max(0.5, float(body.get("minRr") or 2.0)),
        maxRiskPercent=max(0.05, float(body.get("maxRiskPercent") or 1.0)),
        allowedSessions=[str(s) for s in (body.get("allowedSessions") or ["london", "ny", "asian"])],
        autoExecute=bool(body.get("autoExecute") or False) and btype == "execution",
        orderVolume=max(0.01, float(body.get("orderVolume") or 0.01)),
    )


# ---------------------------------------------------------------- persistence


def _row_to_instance(row: BotInstanceRow) -> BotInstance | None:
    try:
        payload = json.loads(row.payload or "{}")
    except Exception:
        payload = {}
    payload.setdefault("id", row.id)
    payload.setdefault("name", row.name)
    payload.setdefault("type", row.type)
    payload["enabled"] = bool(row.enabled)
    try:
        return BotInstance.model_validate(payload)
    except Exception:
        return None


async def save_instance(inst: BotInstance) -> BotInstance:
    payload = inst.model_dump(mode="json")
    _memory_instances[inst.id] = payload
    if SessionLocal is None:
        return inst
    from datetime import datetime

    try:
        created_dt = datetime.fromisoformat(str(inst.createdAt).replace("Z", "+00:00"))
    except ValueError:
        created_dt = utcnow()
    async with SessionLocal() as session:
        await session.merge(
            BotInstanceRow(
                id=inst.id,
                name=inst.name,
                type=inst.type,
                enabled=1 if inst.enabled else 0,
                payload=json.dumps(payload, default=str),
                created_at=created_dt,
            )
        )
        await session.commit()
    return inst


async def list_instances() -> list[BotInstance]:
    if SessionLocal is None:
        out = []
        for payload in _memory_instances.values():
            try:
                out.append(BotInstance.model_validate(payload))
            except Exception:
                continue
        return sorted(out, key=lambda i: i.createdAt)
    async with SessionLocal() as session:
        result = await session.execute(select(BotInstanceRow).order_by(BotInstanceRow.created_at))
        rows = [_row_to_instance(row) for row in result.scalars()]
        return [r for r in rows if r is not None]


async def get_instance(bot_id: str) -> BotInstance | None:
    if not bot_id:
        return None
    if SessionLocal is None:
        payload = _memory_instances.get(bot_id)
        if payload is None:
            return None
        try:
            return BotInstance.model_validate(payload)
        except Exception:
            return None
    async with SessionLocal() as session:
        row = await session.get(BotInstanceRow, bot_id)
        return None if row is None else _row_to_instance(row)


async def delete_instance(bot_id: str) -> bool:
    existed = _memory_instances.pop(bot_id, None) is not None
    if SessionLocal is None:
        return existed
    async with SessionLocal() as session:
        row = await session.get(BotInstanceRow, bot_id)
        if row is None:
            return existed
        await session.delete(row)
        await session.commit()
        return True


async def reset_instances_store() -> None:
    """Tests: clear memory + table + seed marker."""
    _memory_instances.clear()
    await kv_set(SEED_KEY, "")
    if SessionLocal is None:
        return
    async with SessionLocal() as session:
        await session.execute(delete(BotInstanceRow))
        await session.commit()


async def ensure_default_instance() -> BotInstance | None:
    """First boot with no instances: mirror the global gold-bot settings once."""
    if await kv_get(SEED_KEY):
        existing = await get_instance(DEFAULT_BOT_ID)
        return existing
    rows = await list_instances()
    if rows:
        await kv_set(SEED_KEY, "1")
        return next((r for r in rows if r.id == DEFAULT_BOT_ID), None)
    from app.services.settings_store import load_runtime_settings

    runtime = await load_runtime_settings()
    inst = BotInstance(
        id=DEFAULT_BOT_ID,
        name=DEFAULT_BOT_NAME,
        type="strategy",
        enabled=bool(getattr(runtime, "botEnabled", False)),
        scanIntervalSeconds=max(5, int(getattr(runtime, "botScanInterval", 60) or 60)),
        agents=list(getattr(runtime, "botAgents", None) or AGENT_KINDS),
        strategyIds=list(getattr(runtime, "botActiveStrategies", None) or []),
        minRr=float(getattr(runtime, "botMinRr", 2.0) or 2.0),
        maxRiskPercent=float(getattr(runtime, "botMaxRiskPercent", 1.0) or 1.0),
        allowedSessions=list(getattr(runtime, "botAllowedSessions", None) or ["london", "ny", "asian"]),
    )
    await save_instance(inst)
    await kv_set(SEED_KEY, "1")
    logger.info("Default gold bot instance migrated from global settings")
    return inst


# ------------------------------------------------------------------ execution


async def assert_execution_allowed() -> None:
    """Execution bots may only exist while the MT5 account is reachable."""
    from app.services import metaapi

    if not await metaapi.is_connected():
        raise ExecutionNotAllowed("حساب MT5 غير متصل — لا يمكن إنشاء أو تفعيل بوت تنفيذ بدون اتصال فعّال بالوسيط")


async def execute_signal_order(signal_id: str, *, trigger: str) -> dict[str, Any] | None:
    """Place the MT5 market order for an execution-bot signal.

    Never bypasses Pause and never fires without a connected MT5 account.
    Returns the broker result dict, or None when nothing was (or could be) sent.
    """
    from app.services.trading_bot.store import get_signal, update_signal

    signal = await get_signal(signal_id)
    if signal is None:
        return None
    metadata = dict(signal.get("metadata") or {})
    bot_id = str(signal.get("botId") or metadata.get("botId") or "")
    inst = await get_instance(bot_id)
    if inst is None or inst.type != "execution":
        return None
    previous = metadata.get("order")
    if isinstance(previous, dict) and not previous.get("error"):
        return previous  # already executed once
    from app.services.run_control import is_paused

    if await is_paused():
        logger.info("Order for %s skipped: system paused", signal_id)
        return None
    from app.services import metaapi

    if not await metaapi.is_connected():
        logger.info("Order for %s skipped: MT5 not connected", signal_id)
        return None
    side = "BUY" if str(signal.get("signalType") or "buy").lower() == "buy" else "SELL"
    result = await metaapi.place_market_order(
        MT5_GOLD_SYMBOL,
        side,
        float(inst.orderVolume or 0.01),
        stop_loss=float(signal.get("stopLoss") or 0) or None,
        take_profit=float(signal.get("takeProfit1") or 0) or None,
        comment=f"FoxAgent {inst.id}"[:26],
    )
    metadata["order"] = result
    metadata["orderTrigger"] = trigger
    metadata["executedAt"] = utcnow().isoformat()
    patch: dict[str, Any] = {"metadata": metadata}
    if trigger == "auto" and not result.get("error"):
        patch["status"] = "executed"
    await update_signal(signal_id, patch)
    return result


# -------------------------------------------------------------------- manager


class BotRunner:
    """One asyncio loop per non-default instance. Pause freezes the cycle."""

    def __init__(self, instance: BotInstance) -> None:
        from app.services.trading_bot.coordinator import TradingBotCoordinator

        self.instance = instance
        self.coordinator = TradingBotCoordinator()
        self.coordinator.instance = instance
        self.task: asyncio.Task | None = None
        self.started_at: float | None = None

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def update(self, instance: BotInstance) -> None:
        self.instance = instance
        self.coordinator.instance = instance

    def start(self) -> None:
        if self.running:
            return
        self.started_at = time.time()
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self.task
        self.task = None
        self.started_at = None
        if task is None:
            return
        try:
            task.cancel()
            await task
        except (asyncio.CancelledError, Exception):
            pass

    async def _loop(self) -> None:
        while True:
            interval = max(5, int(self.instance.scanIntervalSeconds or 60))
            try:
                from app.services.run_control import is_paused

                if await is_paused() or not self.instance.enabled:
                    await asyncio.sleep(interval)
                    continue
                saved = await self.coordinator.run_cycle()
                self.instance.stats.cycles += 1
                self.instance.stats.lastError = ""
                if saved:
                    self.instance.stats.lastSignalAt = utcnow().isoformat()
                await save_instance(self.instance)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.instance.stats.lastError = str(exc)[:240]
                logger.error("Bot instance %s loop error: %s", self.instance.id, exc)
                try:
                    await save_instance(self.instance)
                except Exception:
                    pass
            await asyncio.sleep(interval)


class BotManager:
    """Starts/stops one loop per enabled instance. The default gold bot keeps
    running on the legacy global coordinator so its API surface stays intact."""

    def __init__(self) -> None:
        self._runners: dict[str, BotRunner] = {}

    # ----- helpers

    def _legacy_coordinator(self):
        from app.services.trading_bot.coordinator import get_coordinator

        return get_coordinator()

    async def ensure_default(self) -> BotInstance | None:
        inst = await ensure_default_instance()
        if inst is not None:
            self._legacy_coordinator().instance = inst
        return inst

    async def _sync_bot_enabled(self, enabled: bool) -> None:
        from app.services.settings_store import load_runtime_settings, save_runtime_settings

        try:
            runtime = await load_runtime_settings()
            if bool(getattr(runtime, "botEnabled", False)) != enabled:
                runtime.botEnabled = enabled
                await save_runtime_settings(runtime)
        except Exception as exc:
            logger.warning("Could not sync botEnabled: %s", exc)

    def instance_snapshot(self, inst: BotInstance) -> dict[str, Any]:
        data = inst.model_dump(mode="json")
        data["isDefault"] = inst.id == DEFAULT_BOT_ID
        if inst.id == DEFAULT_BOT_ID:
            coord = self._legacy_coordinator()
            data["running"] = bool(coord.is_running)
            data["stats"]["cycles"] = max(int(data["stats"].get("cycles") or 0), int(coord.cycles or 0))
            if coord.last_error:
                data["stats"]["lastError"] = coord.last_error
        else:
            runner = self._runners.get(inst.id)
            data["running"] = bool(runner and runner.running)
        return data

    async def list_snapshots(self) -> list[dict[str, Any]]:
        return [self.instance_snapshot(inst) for inst in await list_instances()]

    def refresh(self, inst: BotInstance) -> None:
        """Push edited config into a live runner without restarting it."""
        runner = self._runners.get(inst.id)
        if runner is not None:
            runner.update(inst)
        if inst.id == DEFAULT_BOT_ID:
            coord = self._legacy_coordinator()
            if coord.instance is not None:
                coord.instance = inst

    # ----- lifecycle

    async def start_instance(self, bot_id: str) -> dict[str, Any]:
        inst = await get_instance(bot_id)
        if inst is None:
            raise KeyError(bot_id)
        if inst.type == "execution":
            await assert_execution_allowed()
        if not inst.enabled:
            inst.enabled = True
            await save_instance(inst)
        from app.services.run_control import is_paused

        paused = await is_paused()
        if inst.id == DEFAULT_BOT_ID:
            await self._sync_bot_enabled(True)
            coord = self._legacy_coordinator()
            coord.instance = inst
            if not paused:
                await coord.start()
        elif not paused:
            runner = self._runners.get(bot_id)
            if runner is None:
                runner = BotRunner(inst)
                self._runners[bot_id] = runner
            else:
                runner.update(inst)
            runner.start()
        return {**self.instance_snapshot(inst), "paused": paused}

    async def stop_instance(self, bot_id: str, *, disable: bool = True) -> dict[str, Any]:
        inst = await get_instance(bot_id)
        if inst is None:
            raise KeyError(bot_id)
        if disable and inst.enabled:
            inst.enabled = False
            await save_instance(inst)
        if inst.id == DEFAULT_BOT_ID:
            if disable:
                await self._sync_bot_enabled(False)
            await self._legacy_coordinator().stop()
        else:
            runner = self._runners.get(bot_id)
            if runner is not None:
                runner.update(inst)
                await runner.stop()
        return self.instance_snapshot(inst)

    async def remove_instance(self, bot_id: str) -> bool:
        runner = self._runners.pop(bot_id, None)
        if runner is not None:
            await runner.stop()
        if bot_id == DEFAULT_BOT_ID:
            coord = self._legacy_coordinator()
            await coord.stop()
            coord.instance = None
            await self._sync_bot_enabled(False)
        return await delete_instance(bot_id)

    async def start_enabled(self) -> None:
        """Start every enabled non-default instance (lifespan/resume path).
        The default gold bot follows the legacy botEnabled autostart."""
        from app.services.run_control import is_paused

        if await is_paused():
            return
        for inst in await list_instances():
            if inst.id == DEFAULT_BOT_ID or not inst.enabled:
                continue
            try:
                await self.start_instance(inst.id)
            except ExecutionNotAllowed as exc:
                logger.warning("Execution bot %s left stopped: %s", inst.id, exc)
            except Exception as exc:
                logger.warning("Bot instance %s autostart failed: %s", inst.id, exc)

    async def stop_all(self) -> None:
        for runner in list(self._runners.values()):
            await runner.stop()

    async def on_pause_changed(self, paused: bool) -> None:
        """Manual Pause stops every bot; resume restarts the enabled ones.
        The legacy coordinator (default bot) is handled by run_control directly."""
        if paused:
            await self.stop_all()
            return
        await self.start_enabled()


def get_manager() -> BotManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = BotManager()
    return _MANAGER


def reset_manager() -> BotManager:
    global _MANAGER
    _MANAGER = BotManager()
    return _MANAGER
