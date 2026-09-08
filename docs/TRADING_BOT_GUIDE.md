# دليل بوت تداول الذهب / Gold trading bot guide

FoxAgent's gold bot is a **signal desk**, not a broker. It watches **XAU_USD only**, writes candidate setups, and still cannot bypass `enforce_risk_gate`.

بوت الذهب مكتب إشارات لا وسيط. يراقب **XAU_USD فقط**، يكتب إعدادات مرشّحة، ولا يتجاوز بوابة المخاطر أبداً.

---

## الوكلاء الثلاثة / The three agents

| Agent | Arabic | What it does |
| --- | --- | --- |
| `multi_strategy` | الاستراتيجيات المتعددة | Scans **active** library strategies (5 builtins + approved custom) |
| `pattern_notes` | ملاحظات الأنماط | Detects ten candlestick notes and scores them from `pattern_memory` |
| `news_candle` | شمعة الأخبار | Times entries around real USD prints (NFP, CPI, FOMC, …) |

The coordinator (`TradingBotCoordinator`) runs them about every `botScanInterval` seconds (default 60). **Pause stops the loop.** Resume restarts it only if `botEnabled` is true.

المنسّق يشغّلهم كل `botScanInterval` ثانية. **Pause يوقف الحلقة.** Resume يعيد التشغيل فقط إن كان البوت مفعّلاً.

---

The gold bot and the backtest engine read strategies from **one** `StrategyLibrary`. Claude can propose drafts via `propose_strategy`; the operator validates them on two years of warehouse candles. Rejected rows stay with a reason. Built-ins are never deleted.

البوت والباك تست يقرآن من **مكتبة واحدة**. Claude يقترح مسودات؛ المشغّل يتحقق عبر باك تست سنتين. الرفض لا يحذف الصف. المدمج لا يُحذف.

واجهة المختبر: `/strategy-lab`. REST: `/api/strategies`.

## خمس استراتيجيات ذهب / Five gold strategies

| id | الاسم | الأطر | الفكرة |
| --- | --- | --- | --- |
| `gold_liquidity_sniper` | قناص سيولة الذهب | M5, M15 | كنس سيولة آسيا ثم ارتداد من FVG |
| `gold_breakout` | كسر نطاق الذهب | M15, H1 | كسر نطاق آسيا مع إعادة اختبار |
| `gold_trend_follow` | تتبع اتجاه الذهب | H1, H4 | الدخول مع اتجاه H4 عند FVG/OB |
| `gold_reversal` | انعكاس الذهب | M15, H1 | رفض عند مناطق عرض/طلب |
| `gold_scalp` | سكالبينج الذهب | M1, M5 | زخم سريع ووقف ضيق |

Each strategy implements condition check, entry (FVG/OB mid or close pad), stop (swing ± ATR), targets at **1.5R and 3R**, and a 0–1 confidence score. Structure comes from `analyze_structure()` — swings, FVG, order blocks, Asian range, liquidity sweep.

كل استراتيجية تفحص الشروط، تحسب الدخول والوقف، وتضع هدفين عند 1.5R و 3R. التحليل الهيكلي من `analysis.py`.

---

## عشرة أنماط شموع / Ten candlestick notes

| pattern | الاسم |
| --- | --- |
| `engulfing` | ابتلاع |
| `pin_bar` | بين بار |
| `doji` | دوجي |
| `three_white_soldiers` | ثلاثة جنود بيض |
| `three_black_crows` | ثلاثة غربان سود |
| `inside_bar` | بار داخلي |
| `outside_bar` | بار خارجي |
| `hammer` | مطرقة |
| `shooting_star` | شهاب |
| `morning_evening_star` | نجمة الصباح/المساء |

Reliability starts at 0.55 and moves with the win rate stored in `pattern_memory` after you mark a signal `won` / `lost`.

الموثوقية تبدأ من 0.55 وتتحدّث من نتائج الصفقات السابقة.

---

## أربع استراتيجيات أخبار / Four news plays

| id | التوقيت | القرار |
| --- | --- | --- |
| `pre_news_gold` | قبل الخبر بـ 1–12 دقيقة | أوامر معلّقة حول السعر |
| `news_momentum_gold` | 0–3 دقائق بعد الخبر | مع اتجاه الشمعة الأولى إن كان الجسم ≥ 70% |
| `news_retracement_gold` | 5–10 دقائق | انتظار ارتداد بعد الشمعة القوية |
| `news_fade_gold` | 10–20 دقيقة | عكس الحركة عند المبالغة |

News-candle rules: large body + volume → momentum; long upper wick → sell; long lower wick → buy; doji → wait.

شمعة قوية + حجم → زخم. ظل علوي كبير → بيع. ظل سفلي كبير → شراء. دوجي → انتظار.

Events come from the real USD calendar (`economic_calendar.py`). If scraping fails, the list is empty — the bot does **not** invent NFP/CPI.

الأحداث من التقويم الحقيقي. إن فشل الكشط تبقى القائمة فارغة — لا اختلاق.

---

## التشغيل والإيقاف / Start and stop

1. Settings → enable «بوت الذهب» / Gold bot, or open `/bot` and press Start.
2. The API sets `botEnabled=true` and starts the monitor unless the desk is paused.
3. Stop sets `botEnabled=false` and cancels the task.
4. System Pause always stops the bot. Resume starts it again only when enabled.
5. Tests set `FOXAGENT_BOT_AUTOSTART=0` so pytest never leaves a live loop.

```http
POST /api/bot/start
POST /api/bot/stop
GET  /api/bot/status
```

The bot **never** calls OANDA order endpoints.

البوت لا يستدعي أبداً مسارات أوامر OANDA.

---

## إدارة المخاطر / Risk

Two layers, both mandatory:

1. **Sacred gate** — `minRiskReward`, `maxRiskPercent`, `allowedSessions`.
2. **Bot caps** — `botMinRr` (default 2.0), `botMaxRiskPercent` (default 1.0), `botAllowedSessions`.

A rejected signal is logged and discarded. High-confidence (> 0.8) signals can be converted to a full recommendation; that path calls `persist_recommendation` and the same gate again.

إشارة مرفوضة تُهمل. إشارة بثقة أعلى من 0.8 يمكن تحويلها لتوصية كاملة عبر البوابة نفسها.

---

## تفسير الإشارات / Reading a signal

| Field | معنى |
| --- | --- |
| `strategyId` | أي استراتيجية أو نمط أطلق الإشارة |
| `signalType` | `buy` / `sell` |
| `entryPrice` / `stopLoss` / `takeProfit1` / `takeProfit2` | 1.5R و 3R |
| `confidence` | 0–1 |
| `riskReward` | عادة 3.0 عند الهدف الثاني |
| `status` | `pending`, `active`, `won`, `lost`, `expired` |

Promoting writes a `TradeRecommendation` with entry overlay and shows it on `/recommendations`.

التحويل يكتب توصية تظهر في صفحة التوصيات.

---

## أمثلة عملية / Worked examples

**Liquidity sniper.** Asian low swept on M15, bullish FVG left behind. Entry at FVG midpoint, stop under the sweep wick, TP2 at 3R. If implied risk (`|entry−SL|/entry`) exceeds 1%, the gate drops it.

**News momentum.** CPI prints, first M1 body is 80% of the range with 3× volume. `news_momentum_gold` fires with the candle direction. Telegram `send_bot_signal` fires if notifications are on.

**Pattern memory.** Three engulfing wins on M15 raise reliability; later engulfing signals carry a higher confidence.

قناص السيولة يدخل من منتصف FVG بعد كنس آسيا. زخم الخبر يدخل مع الشمعة الأولى. الأنماط تتعلّم من النتائج.

---

## بيانات الشموع / Candle source

1. `gold_warehouse` for M15 / H1 / H4 / D (two-year window).
2. OANDA REST if the warehouse has no bars (M1/M5 always miss the warehouse).
3. Deterministic simulator if both are empty.

Rate limits and backoff stay inside `oanda.py`. The bot does not add extra polling beyond the scan interval.

---

## إعدادات المشغّل / Operator settings

| Key | Default |
| --- | --- |
| `botEnabled` | `false` |
| `botScanInterval` | `60` |
| `botAgents` | all three |
| `botActiveStrategies` | all five gold strategies |
| `botMaxRiskPercent` | `1.0` |
| `botMinRr` | `2.0` |
| `botAllowedSessions` | london, ny, asian |
| `economicCalendarProvider` | `forex_factory` |
| `economicCalendarCacheTtl` | 5 minutes |

See also `docs/FOXAGENT_REFERENCE_AR.md` § التقويم الاقتصادي and § بوت تداول الذهب.
