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
    session = current_session()
    allowed = list(runtime.allowedSessions or [])
    sess_ok = _session_allowed(str(session.get("session") or ""), allowed)
    ok_rr = rr >= float(runtime.minRiskReward)
    reasons: list[str] = []
    if not ok_rr:
        reasons.append(f"R:R {rr:.2f} is below minimum {runtime.minRiskReward}")
    if not sess_ok:
        reasons.append(f"Session {session.get('session')} is not in allowedSessions {allowed}")
    return {
        "ok": ok_rr and sess_ok,
        "actualRr": round(rr, 2),
        "minRiskReward": runtime.minRiskReward,
        "maxRiskPercent": runtime.maxRiskPercent,
        "session": session,
        "sessionAllowed": sess_ok,
        "reasons": reasons,
    }
