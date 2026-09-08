# دليل باك تست الذهب / Gold backtest guide

Deterministic replay of the five ICT gold rules on `gold_candles` (M15 / H1 / H4 / D). **No LLM. No network. No broker orders.**

محاكاة حتمية لقواعد الذهب الخمس على المستودع فقط. لا نموذج لغوي، لا شبكة، لا أوامر وساطة.

---

## التشغيل / How to run

1. Open `/backtest` (الباك تست in the sidebar).
2. Pick timeframe `M15` / `H1` / `H4`, one strategy or all, and 90–730 days.
3. Run. The API is:

```http
POST /api/backtest/run
{
  "timeframe": "M15",
  "strategyId": null,
  "days": 365,
  "riskPercent": 1.0,
  "minRr": 2.0
}
```

`strategyId: null` runs every rule that lists that timeframe. Scalp targets are 1R / 1.5R — use `minRr: 1` if you want those trades included.

The engine loads the warehouse only (`GOLD_WAREHOUSE_SYNC=0` in tests). An empty warehouse returns `candlesTested: 0` and no invented bars.

---

## تفسير النتائج / Reading the numbers

| Metric | Meaning |
| --- | --- |
| **Win rate** | Share of trades with `pnlR > 0` after costs |
| **R** | Multiple of initial risk (`|entry − stop|`). +1R = one full risk unit |
| **Total R** | Sum of every trade’s R |
| **Average R** | Total R / trades |
| **Profit factor** | Gross winning R / abs(gross losing R) |
| **Max drawdown R** | Worst peak-to-trough of the cumulative R curve |
| **pnlPercent** | `pnlR × riskPercent` (default 1R = 1% account risk) |

Partial exit: 50% at TP1 (1.5R except scalp 1R), stop to breakeven, remainder at TP2 or BE / timeout.

Same-bar rule: **stop is checked before TP1**. A bar that tags both is a full loss.

Costs on every trade: slippage **$0.20** on the fill (next-bar open) and spread **$0.35** converted to R.

---

## الحدود / Limits

- Paper simulation only. It does not model queue position, news spikes, or dynamic slippage.
- No M1/M5 — those frames are absent from the warehouse.
- No lookahead: signal at bar `i` sees `[i-120 … i]`; fill is `i+1` open.
- One open trade per strategy at a time.
- Results on a thin or gappy warehouse are not comparable to a full two-year book.
- The live bot still cannot bypass the risk gate; this report does not place orders.

---

## مقارنة الاستراتيجيات / Comparing rules

| id | Frames | Hold (bars) | Notes |
| --- | --- | --- | --- |
| `gold_liquidity_sniper` | M15 | 48 | Asian sweep + FVG + BOS |
| `gold_breakout` | M15, H1 | 24 | Close through Asian range |
| `gold_trend_follow` | H1, H4 | 120 | Bias + FVG/OB |
| `gold_reversal` | M15, H1 | 36 | Rejection at OB |
| `gold_scalp` | M15 | 6 | Impulse; 1R / 1.5R |

`byStrategy` / `bySession` / `byMonth` in the JSON (and the comparison table) are the same rollup: trades, wins, win rate, total R.

Reports persist in `backtest_reports` (`GET /api/backtest/reports`).

See `docs/FOXAGENT_REFERENCE_AR.md` §10.3 and `docs/TRADING_BOT_GUIDE.md` for the live signal bot (separate from this replay).
