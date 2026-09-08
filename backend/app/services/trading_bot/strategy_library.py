"""Central gold strategy library — single source of truth for bot and backtest."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.schemas import new_id
from app.services.trading_bot.models import StrategyRecord
from app.services.trading_bot.strategy_schema import (
    BUILTIN_IDS,
    StrategyRule,
    builtin_rules,
    evaluate_thresholds,
    sanitize_timeframes,
    utcnow,
)

logger = logging.getLogger(__name__)

_memory: dict[str, dict[str, Any]] = {}
_LIBRARY: "StrategyLibrary | None" = None

_KEY_ALIASES = {
    "entryConditions": "entry_conditions",
    "stopRule": "stop_rule",
    "tp1R": "tp1_r",
    "tp2R": "tp2_r",
    "maxHoldingBars": "max_holding_bars",
    "createdBy": "created_by",
    "validationReportId": "validation_report_id",
    "rejectionReason": "rejection_reason",
}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:40]
    return slug or new_id("st")


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    for src, dest in _KEY_ALIASES.items():
        if src in out and dest not in out:
            out[dest] = out[src]
    if "timeframe" in out and "timeframes" not in out:
        raw = out["timeframe"]
        out["timeframes"] = raw if isinstance(raw, list) else [raw]
    return out


def _public(rule: StrategyRule) -> dict[str, Any]:
    data = rule.model_dump(mode="json")
    data["timeframe"] = list(data.get("timeframes") or [])
    return data


def _from_row(payload: dict[str, Any]) -> StrategyRule | None:
    try:
        return StrategyRule.model_validate(payload)
    except Exception:
        return None


class StrategyLibrary:
    """المكتبة المركزية — مصدر الحقيقة الوحيد للاستراتيجيات."""

    def __init__(self) -> None:
        self._builtins = {r.id: r for r in builtin_rules()}

    def _merge(self, stored: list[StrategyRule]) -> dict[str, StrategyRule]:
        out = dict(self._builtins)
        for rule in stored:
            if rule.id in self._builtins:
                continue
            out[rule.id] = rule
        return out

    async def _load_stored(self) -> list[StrategyRule]:
        rows: list[dict[str, Any]] = list(_memory.values())
        if SessionLocal is not None:
            async with SessionLocal() as session:
                result = await session.execute(select(StrategyRecord))
                rows = []
                for row in result.scalars():
                    try:
                        payload = json.loads(row.rules or "{}")
                    except json.JSONDecodeError:
                        payload = {}
                    payload.update(
                        {
                            "id": row.id,
                            "name": row.name,
                            "description": row.description,
                            "source": row.source,
                            "created_by": row.created_by,
                            "status": row.status,
                            "validation_report_id": row.validation_report_id,
                            "rejection_reason": row.rejection_reason,
                            "created_at": row.created_at,
                            "validated_at": row.validated_at,
                        }
                    )
                    rows.append(payload)
        out: list[StrategyRule] = []
        for item in rows:
            rule = _from_row(item)
            if rule and rule.id not in self._builtins:
                out.append(rule)
        return out

    async def _persist(self, rule: StrategyRule) -> StrategyRule:
        payload = rule.model_dump(mode="json")
        _memory[rule.id] = payload
        if SessionLocal is None:
            return rule
        async with SessionLocal() as session:
            await session.merge(
                StrategyRecord(
                    id=rule.id,
                    name=rule.name,
                    description=rule.description,
                    rules=json.dumps(payload, default=str),
                    source=rule.source,
                    created_by=rule.created_by,
                    status=rule.status,
                    validation_report_id=rule.validation_report_id,
                    rejection_reason=rule.rejection_reason,
                    created_at=rule.created_at,
                    validated_at=rule.validated_at,
                )
            )
            await session.commit()
        return rule

    async def get_all(self) -> list[StrategyRule]:
        merged = self._merge(await self._load_stored())
        return sorted(merged.values(), key=lambda r: (0 if r.source == "builtin" else 1, r.name))

    async def get(self, strategy_id: str) -> StrategyRule | None:
        if strategy_id in self._builtins:
            return self._builtins[strategy_id]
        merged = self._merge(await self._load_stored())
        return merged.get(strategy_id)

    async def get_active_strategies(self) -> list[StrategyRule]:
        return [r for r in await self.get_all() if r.status == "active"]

    async def list_runnable(self, timeframe: str | None = None) -> list[StrategyRule]:
        rows = [r for r in await self.get_all() if r.status == "active"]
        if timeframe:
            rows = [r for r in rows if timeframe in r.timeframes]
        return rows

    async def propose(self, payload: dict[str, Any], *, source: str = "manual", created_by: str = "operator") -> dict[str, Any]:
        payload = normalize_payload(payload)
        name = str(payload.get("name") or "").strip()
        if not name:
            return {"ok": False, "detail": "name is required"}
        sid = str(payload.get("id") or _slug(name))
        if sid in self._builtins:
            return {"ok": False, "detail": "Cannot overwrite a builtin strategy"}
        existing = await self.get_all()
        if any(r.id == sid for r in existing):
            return {"ok": False, "detail": "Duplicate strategy id", "id": sid}
        if any(r.name.lower() == name.lower() and r.status != "archived" for r in existing):
            return {"ok": False, "detail": "Duplicate strategy name"}
        tfs = sanitize_timeframes(payload.get("timeframes") or payload.get("timeframe"))
        rule = StrategyRule(
            id=sid,
            name=name,
            description=str(payload.get("description") or ""),
            timeframes=tfs,
            direction=payload.get("direction") or "both",  # type: ignore[arg-type]
            entry_conditions=dict(payload.get("entry_conditions") or {}),
            stop_rule=str(payload.get("stop_rule") or "swing ± ATR"),
            tp1_r=float(payload.get("tp1_r") or 1.5),
            tp2_r=float(payload.get("tp2_r") or 3.0),
            max_holding_bars=int(payload.get("max_holding_bars") or 48),
            source=source if source in {"builtin", "claude_proposed", "manual"} else "manual",  # type: ignore[arg-type]
            created_by=created_by,
            status="draft",
        )
        await self._persist(rule)
        return {"ok": True, "strategy": _public(rule)}

    async def validate(
        self,
        strategy_id: str,
        *,
        days: int = 730,
        auto_activate: bool = False,
        engine_run=None,
    ) -> dict[str, Any]:
        from app.services.run_control import is_paused

        if await is_paused():
            return {"ok": False, "paused": True, "detail": "FoxAgent is paused"}
        rule = await self.get(strategy_id)
        if rule is None:
            return {"ok": False, "detail": "Strategy not found"}
        if rule.source == "builtin":
            return {"ok": True, "passed": True, "builtin": True, "strategy": _public(rule)}
        tf = next((t for t in rule.timeframes if t in {"M15", "H1", "H4", "D"}), "M15")
        if engine_run is None:
            from app.services.backtest.engine import BacktestEngine

            async def engine_run(**kwargs):
                return await BacktestEngine().run(**kwargs)

        min_rr = min(float(rule.tp2_r), 2.0)
        report = await engine_run(
            timeframe=tf,
            strategy_id=rule.id,
            days=days,
            min_rr=min_rr,
            persist=True,
            rule=rule,
        )
        passed, reasons = evaluate_thresholds(report)
        rule.validation_report_id = report.id or None
        rule.validated_at = utcnow()
        if passed:
            rule.status = "active" if auto_activate else "validated"
            rule.rejection_reason = None
        else:
            rule.status = "rejected"
            rule.rejection_reason = "; ".join(reasons)
        await self._persist(rule)
        return {
            "ok": True,
            "passed": passed,
            "reasons": reasons,
            "strategy": _public(rule),
            "report": report.model_dump(mode="json") if hasattr(report, "model_dump") else report,
        }

    async def approve(self, strategy_id: str) -> dict[str, Any]:
        rule = await self.get(strategy_id)
        if rule is None:
            return {"ok": False, "detail": "Strategy not found"}
        if rule.source == "builtin":
            return {"ok": True, "strategy": _public(rule)}
        if rule.status not in {"validated", "active"}:
            return {"ok": False, "detail": "Strategy must pass validation before approval"}
        rule.status = "active"
        await self._persist(rule)
        return {"ok": True, "strategy": _public(rule)}

    async def reject(self, strategy_id: str, reason: str = "") -> dict[str, Any]:
        rule = await self.get(strategy_id)
        if rule is None:
            return {"ok": False, "detail": "Strategy not found"}
        if rule.source == "builtin":
            return {"ok": False, "detail": "Cannot reject a builtin strategy"}
        rule.status = "rejected"
        rule.rejection_reason = reason or rule.rejection_reason or "rejected by operator"
        await self._persist(rule)
        return {"ok": True, "strategy": _public(rule)}

    async def archive(self, strategy_id: str) -> dict[str, Any]:
        rule = await self.get(strategy_id)
        if rule is None:
            return {"ok": False, "detail": "Strategy not found"}
        if rule.source == "builtin":
            return {"ok": False, "detail": "Cannot archive a builtin strategy"}
        rule.status = "archived"
        await self._persist(rule)
        return {"ok": True, "strategy": _public(rule)}

    async def patch(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_payload(payload)
        rule = await self.get(strategy_id)
        if rule is None:
            return {"ok": False, "detail": "Strategy not found"}
        if rule.source == "builtin":
            return {"ok": False, "detail": "Cannot edit a builtin strategy"}
        if rule.status != "draft":
            return {"ok": False, "detail": "Only drafts can be edited"}
        data = rule.model_dump()
        for key in ("name", "description", "direction", "stop_rule", "tp1_r", "tp2_r", "max_holding_bars", "entry_conditions"):
            if key in payload:
                data[key] = payload[key]
        if payload.get("timeframes") or payload.get("timeframe"):
            data["timeframes"] = sanitize_timeframes(payload.get("timeframes") or payload.get("timeframe"))
        updated = StrategyRule.model_validate(data)
        await self._persist(updated)
        return {"ok": True, "strategy": _public(updated)}

    async def delete(self, strategy_id: str) -> dict[str, Any]:
        rule = await self.get(strategy_id)
        if rule is None:
            return {"ok": False, "detail": "Strategy not found"}
        if rule.source == "builtin":
            return {"ok": False, "detail": "Cannot delete a builtin strategy"}
        if rule.status != "draft":
            return {"ok": False, "detail": "Only drafts can be deleted — reject or archive instead"}
        _memory.pop(strategy_id, None)
        if SessionLocal is not None:
            async with SessionLocal() as session:
                row = await session.get(StrategyRecord, strategy_id)
                if row:
                    await session.delete(row)
                    await session.commit()
        return {"ok": True, "deleted": strategy_id}


def get_library() -> StrategyLibrary:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = StrategyLibrary()
    return _LIBRARY


def reset_library() -> StrategyLibrary:
    global _LIBRARY
    _memory.clear()
    _LIBRARY = StrategyLibrary()
    return _LIBRARY


async def reset_library_store() -> StrategyLibrary:
    """Clear in-memory drafts and persisted non-builtin rows (tests)."""
    lib = reset_library()
    if SessionLocal is not None:
        async with SessionLocal() as session:
            result = await session.execute(select(StrategyRecord))
            for row in result.scalars().all():
                await session.delete(row)
            await session.commit()
    return lib
