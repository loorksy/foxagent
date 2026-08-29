from __future__ import annotations

from typing import Any

from app.services.macro_feed import current_session
from app.services.settings_store import load_runtime_settings


def _session_allowed(name: str, allowed: list[str]) -> bool:
    allowed_l = {s.lower() for s in allowed}
    if name in allowed_l:
        return True
    if name == "london_ny_overlap":
        return "london" in allowed_l or "ny" in allowed_l
    if name == "late_ny_asia":
        return "ny" in allowed_l or "asian" in allowed_l
    return False


class RiskRejected(Exception):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        super().__init__("; ".join(result.get("reasons") or ["risk gate"]))


def implied_risk_percent(entry: float, stop_loss: float, explicit: float | None = None) -> float:
    """Account-style risk % is not on the payload; use explicit riskPercent or |entry-SL|/entry."""
    if explicit is not None and explicit > 0:
        return float(explicit)
    if not entry:
        return 0.0
    return abs(entry - stop_loss) / abs(entry) * 100.0


async def validate_risk_rules(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = await load_runtime_settings()
    setup = payload.get("tradeSetup") or payload
    entry = float(setup.get("entryPrice") or 0)
    sl = float(setup.get("stopLoss") or 0)
    rr = float(setup.get("riskRewardRatio") or 0)
    tps = setup.get("takeProfitLevels") or []
    if rr <= 0 and entry and sl and tps:
        last = tps[-1]
        tp = float(last.get("price") or 0)
        risk = abs(entry - sl)
        if risk:
            rr = abs(tp - entry) / risk
    explicit = setup.get("riskPercent")
    if explicit is None:
        explicit = payload.get("riskPercent")
    risk_pct = implied_risk_percent(entry, sl, float(explicit) if explicit not in (None, "") else None)
    session = current_session()
    allowed = list(runtime.allowedSessions or [])
    sess_ok = _session_allowed(str(session.get("session") or ""), allowed)
    ok_rr = rr >= float(runtime.minRiskReward)
    ok_risk = risk_pct <= float(runtime.maxRiskPercent)
    reasons: list[str] = []
    if not ok_rr:
        reasons.append(f"R:R {rr:.2f} is below minimum {runtime.minRiskReward}")
    if not sess_ok:
        reasons.append(f"Session {session.get('session')} is not in allowedSessions {allowed}")
    if not ok_risk:
        reasons.append(
            f"Implied risk {risk_pct:.2f}% exceeds maxRiskPercent {runtime.maxRiskPercent}"
        )
    return {
        "ok": ok_rr and sess_ok and ok_risk,
        "actualRr": round(rr, 2),
        "impliedRiskPercent": round(risk_pct, 4),
        "minRiskReward": runtime.minRiskReward,
        "maxRiskPercent": runtime.maxRiskPercent,
        "session": session,
        "sessionAllowed": sess_ok,
        "reasons": reasons,
    }


async def enforce_risk_gate(payload: dict[str, Any]) -> dict[str, Any]:
    result = await validate_risk_rules(payload)
    if not result["ok"]:
        raise RiskRejected(result)
    return result
