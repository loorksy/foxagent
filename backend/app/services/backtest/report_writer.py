"""Readable Arabic/English backtest summary."""

from __future__ import annotations

from app.services.backtest.models import BacktestReport


def generate_text_report(report: BacktestReport) -> str:
    best = "—"
    worst = "—"
    ranked = sorted(
        ((sid, stats) for sid, stats in report.byStrategy.items() if stats.get("trades")),
        key=lambda item: item[1].get("totalR") or 0,
        reverse=True,
    )
    if ranked:
        best = f"{ranked[0][0]} ({ranked[0][1].get('totalR'):+.2f}R)"
        worst = f"{ranked[-1][0]} ({ranked[-1][1].get('totalR'):+.2f}R)"
    scope = report.strategyId or "all"
    wr = report.winRate * 100.0
    return (
        "┌─────────────────────────────────┐\n"
        f"│  باك تست الذهب — {report.timeframe} — {report.days} يوم  │\n"
        f"│  Gold backtest — {scope}              │\n"
        "├─────────────────────────────────┤\n"
        f"│ الصفقات / Trades: {report.totalTrades:<13}│\n"
        f"│ معدل النجاح / Win: {wr:5.1f}%          │\n"
        f"│ مجموع R / Total R: {report.totalR:+.2f}           │\n"
        f"│ Profit Factor: {report.profitFactor:<14}│\n"
        f"│ أقصى تراجع / DD: -{report.maxDrawdownR:.2f}R          │\n"
        "├─────────────────────────────────┤\n"
        f"│ أفضل / Best: {best:<18}│\n"
        f"│ أسوأ / Worst: {worst:<17}│\n"
        "└─────────────────────────────────┘\n"
        "ورقي فقط — بلا تنفيذ وساطة. Paper only — no broker orders.\n"
    )
