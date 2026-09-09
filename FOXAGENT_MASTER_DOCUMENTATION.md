# FoxAgent — المرجع التقني والتشغيلي الشامل

وثيقة مرجعية مستخرجة من شيفرة المستودع كما هي على `main` عند الدمج `b15a9ec` (PR #12). لا تعتمد على تخمين أو قوالب. كل ثابت ومسار واستدعاء مذكور هنا موجود في الملفات المشار إليها.

**ما هو FoxAgent؟** محطة عمل لمشغّل واحد، ذهب فقط (`XAU_USD`)، تحليل ICT/SMC عبر طاقم Claude، بوت إشارات لا يضع أوامر وسيط، مستودع شموع محلي، وبوابة مخاطر حتمية في بايثون. الواجهة عربية RTL افتراضياً. التشغيل الحي: `https://foxagent.lork.cloud`.

**ما الذي لا يفعله النظام؟** لا يرسل أوامر شراء/بيع إلى OANDA. البوت يكتب إشارات في SQLite وينتظر اعتماد المشغّل. لا يوجد `eval` ولا تنفيذ بايثون حر من النموذج. لا تُختلق أخبار ولا شموع عند فشل المصدر.

---

## 1. المعمارية العامة ومخطط التدفق (System Architecture & Data Flow)

### 1.1 خريطة الطبقات

النشر المعزول في `deploy/docker-compose.yml` بمشروع Docker اسمه `foxagent` ومنفذ مضيف واحد (افتراضي `18180`):

```
المشغّل (متصفح)
        │
        ▼
┌───────────────────┐
│ Caddy 2.8 :18180  │  deploy/Caddyfile
│  /api/*  → backend:8000
│  /ws/*   → backend:8000
│  *       → frontend:3000
└───────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
Next.js 14   FastAPI 1.0.0
:3000        :8000
AuthGate     lifespan + حلقات asyncio
Zustand      SQLite WAL  /data/foxagent.db
klinecharts  EventBus (ذاكرة + Redis اختياري)
```

| طبقة | الحاوية | الدور الفعلي في الكود |
|---|---|---|
| الحافة | `foxagent-edge` (`caddy:2.8-alpine`) | توجيه `/api/*` و`/ws/*` إلى الخلفية، والباقي إلى Next.js. ضغط gzip. |
| الواجهة | `foxagent-frontend` | `BACKEND_URL=http://backend:8000` و`NEXT_PUBLIC_WS_SAME_ORIGIN=1`. |
| الخلفية | `foxagent-backend` | FastAPI على `:8000`. المجلد `foxagent_data:/data`. |
| البيانات | حجم Docker `foxagent_data` | `DATABASE_URL=sqlite+aiosqlite:////data/foxagent.db` و`FOXAGENT_DATA_DIR=/data`. |
| الناقل | `app.bus.EventBus` | نشر محلي دائماً. إن وُجد `REDIS_URL` ينشر أيضاً على قناة `foxagent:{topic}` ويشترك بـ `foxagent:*`. |

لا يوجد Redis في `docker-compose.yml` الافتراضي. الناقل يبقى داخل العملية ما لم يُحقن `redis_url` يدوياً.

### 1.2 دورة حياة العملية (`backend/app/main.py`)

`lifespan` بالترتيب:

1. `logging.basicConfig`
2. `init_db()` — تسجيل جداول إضافية ثم `create_all`، ثم `PRAGMA journal_mode=WAL` و`PRAGMA busy_timeout=30000`، ثم `get_library().get_all(hydrate=True)`.
3. `bus.connect()` — يحاول Redis إن وُجد العنوان.
4. `load_runtime_settings()` ثم `apply_runtime_to_env()` — فك تشفير KV `runtime_settings` وحقن الأسرار في كائن `Settings` المخزّن بـ `@lru_cache`.
5. أربع مهام asyncio:
   - `price_pump()` فوراً
   - `_reflection_loop()` — انتظار **8 ثوانٍ** ثم دورة كل **45 ثانية**
   - `gold_sync_loop()` — انتظار **4 ثوانٍ** ثم دورة كل **60 ثانية**
   - `_ops_loop()` — انتظار **20 ثانية** ثم دورة كل **60 ثانية**
6. إن `FOXAGENT_BOT_AUTOSTART` ليست `0/false/off/no` **و** `runtime.botEnabled` **و** النظام غير متوقف: `bot.start()`.
7. عند الإغلاق: `await bot.stop()` ثم `cancel()` لأربع المهام **دون انتظارها** (`await` غير موجود بعد الإلغاء).

إن فشل فتح SQLite يسقط `init_db` إلى مخازن قواميس في الذاكرة (`_memory_recs`, `_memory_settings`) وتستمر العملية بلا قرص.

### 1.3 دورة حياة الطلب والحماية

ترتيب الوسائط في `create_app()` (آخر مضاف يُنفَّذ أولاً في Starlette):

1. `CORSMiddleware` — أصول من `CORS_ORIGINS` أو `*` مع `allow_credentials=True`.
2. `AuthMiddleware` — كل مسار يبدأ بـ `/api/` عدا `PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/logout"}`.
3. `RateLimitMiddleware` — **180 طلباً / 60 ثانية / عنوان IP**، يتخطى غير `/api/` وكذلك `/api/health` و`/api/auth/login`. المخزن قاموس داخل العملية (`self.hits`)، ليس Redis.

**ملاحظة تشغيلية:** `/api/health` مستثنى من حد المعدل لكنه **ليس** عاماً في المصادقة. مراقب خارجي بلا كوكي JWT يتلقى `401`.

المصادقة (`backend/app/auth.py`):

| عنصر | القيمة في الكود |
|---|---|
| الكوكي | `foxagent_token`، `httponly=True`، `samesite=lax`، `path=/`، `max_age = jwt_expire_minutes * 60` |
| الخوارزمية | JWT HS256 |
| الحمولة | `sub=operator`، `iat`، `exp` |
| مدة الصلاحية الافتراضية | `jwt_expire_minutes=720` (12 ساعة) |
| استخراج الرمز | `Authorization: Bearer` ثم الكوكي ثم `?token=` (REST وWebSocket) |
| كلمة المرور | `ADMIN_PASSWORD_HASH` (bcrypt) أولاً، وإلا مقارنة ثابتة الزمن مع `APP_PASSWORD` |
| سر JWT | `jwt_secret` أو `settings_secret`، وإن خلا كلاهما: السلسلة الثابتة `foxagent-dev-jwt-secret` |

مسارات WebSocket `/ws/market` و`/ws/bot` ترفض الاتصال برمز `1008` إن فشل الرمز.

تشفير الإعدادات (`backend/app/services/settings_store.py`):

- المفتاح: `SETTINGS_SECRET` / `settings_secret` يُمرَّر عبر SHA-256 ثم Base64 إلى Fernet، أو ملف `.foxagent.key` تحت `FOXAGENT_DATA_DIR` ثم `/data` ثم `backend/data`.
- القيمة المخزّنة في جدول `settings` بالمفتاح `runtime_settings` هي رمز Fernet لنص JSON كامل لـ `SettingsPayload`.
- إن فشل فك التشفير يُجرَّب JSON صريح (ترحيل قديم).
- `GET /api/settings` يعيد `SettingsPublic` بأقنعة (`anthropicApiKeySet` إلخ) لا الأسرار.

الحقول الحسّاسة في `SettingsPayload` (`backend/app/schemas.py`): `anthropicApiKey`, `oandaApiToken`, `oandaAccountId`, `oandaEnvironment`, `telegramBotToken`, `telegramChatId`, حدود المخاطر، إعدادات البوت، ومزوّد التقويم.

### 1.4 حلقات الخلفية ومسؤولية كل حلقة

| الحلقة | الملف | التردد | ماذا تفعل | ماذا يفعل Pause |
|---|---|---|---|---|
| `price_pump` | `backend/app/api/ws.py` | بث OANDA مستمر؛ إعادة اتصال بعد **1 ثانية** عند الانقطاع. المحاكي: تكة كل **0.25 ثانية** لكل زوج في `INSTRUMENT_SPECS`. | يبث `{type: tick}` إلى `market_hub` وإلى `bus` موضوع `market`. | ينام 0.25 ثانية ولا يستهلك التيار. إن كان داخل `stream_prices` يكسر الحلقة الداخلية. |
| `gold_sync_loop` | `backend/app/services/gold_sync.py` | انتظار 4 ثوانٍ ثم كل **60 ثانية**. تُعطَّل إن `GOLD_WAREHOUSE_SYNC` في `{0,false,off,no}` أو وُجد `PYTEST_CURRENT_TEST`. | `run_sync_cycle`: لكل إطار في `M15,H1,H4,D` يملأ الفجوات ثم `prune_older_than` لنافذة 730 يوماً. دفعات 5000 شمعة، تأخير 0.4 ثانية، تراجع أسي حتى 6 محاولات عند 429. | تتخطى الدورة وتنام 60 ثانية. |
| `_reflection_loop` | `backend/app/main.py` | انتظار 8 ثوانٍ ثم كل **45 ثانية**. | `scan_closed_recommendations()` يكتب درساً للتوصيات ذات الحالة النهائية. | تتخطى المسح. |
| `_ops_loop` | `backend/app/main.py` | انتظار 20 ثانية ثم كل **60 ثانية**. | إن الساعة UTC = 7 والدقيقة < 20: `send_briefing()`. ثم تنبيه مستودع راكد وتنبيه أخبار عالية الأثر خلال 30 دقيقة. | تتخطى كل الإرسال. |
| `TradingBotCoordinator._monitor_loop` | `backend/app/services/trading_bot/coordinator.py` | `max(5, botScanInterval)` ثانية، الافتراضي **60**. عند خطأ: نوم **30 ثانية** و`note_scan_error()`. | دورة مسح الوكلاء الثلاثة ثم `record_scan`. | `on_pause_changed(True)` يوقف المراقبة بالكامل. داخل الدورة `_accept` يعيد `None`. |
| تجارب المختبر | `backend/app/services/trading_bot/experiment.py` | متزامن داخل طلب HTTP/أداة MCP، حتى **8** محاولات. | يقترح مسودة ثم يُشغّل الباك تست ويُحوّر الأعلام. | `start_experiment` يعيد فوراً `{paused: true}`؛ أثناء الحلقة يضع الحالة `paused` ويكسر. |

`price_pump` **لا** يشارك في مزامنة المستودع. المستودع حلقة مستقلة.

### 1.5 مخطط تدفق البيانات الحية

```mermaid
flowchart LR
  subgraph feed [مصدر السعر]
    OANDA[OANDA v20 stream]
    SIM[TickSimulator seed=42]
  end
  OANDA -->|إن وُجد توكن وحساب| PUMP[price_pump]
  SIM -->|وإلا| PUMP
  PUMP --> HUB[/ws/market Hub]
  PUMP --> BUS[EventBus topic=market]
  HUB --> UI[DeskLayout Zustand prices]
  UI --> CHART[ChartCanvas updateData]
  SYNC[gold_sync_loop كل 60ث] --> DB[(gold_candles)]
  OANDA2[OANDA REST /v3/instruments/.../candles] --> SYNC
  DB --> GET[/api/candles لمستودع الذهب]
  GET --> CHART
```

### 1.6 جداول SQLite الفعلية

`init_db` يستورد الوحدات التالية قبل `create_all` فتسجَّل الجداول على `Base`:

| الجدول | الوحدة | المفتاح / الغرض |
|---|---|---|
| `recommendations` | `app.db.RecommendationRow` | `id`، `payload` JSON كامل لـ `TradeRecommendation` |
| `settings` | `app.db.SettingRow` | KV: `runtime_settings` (Fernet)، `system_paused`، `strategy_pins`، `strategy_circuits`، `desk_safe_mode`، `inbox_acks` |
| `gold_candles` | `gold_warehouse.GoldCandleRow` | مركّب `(timeframe, timestamp)` |
| `memory_entries` | `memory_log.MemoryEntryRow` | دروس مع تضمين معجمي JSON |
| `agent_sessions` | `session_store.SessionRow` | سجل المحادثة والأحداث في `payload` |
| `economic_events` | `economic_calendar.EconomicEventRow` | أحداث USD المخزّنة |
| `pattern_memory` | `trading_bot.models.PatternMemoryRow` | إحصاء أنماط |
| `bot_signals` | `trading_bot.models.BotSignalRow` | إشارات البوت |
| `strategy_performance` | `trading_bot.models.StrategyPerformanceRow` | أداء الوكلاء |
| `strategies` | `trading_bot.models.StrategyRecord` | عقود DSL (غير المضمّنة تُحفظ هنا) |
| `backtest_reports` | `backtest.models` | تقارير الباك تست |

مخازن **داخل العملية فقط** (تُفقد عند إعادة التشغيل): `_SCANS` (حد 400)، `_JOBS` تجارب المختبر، `_ENTRIES` دفتر القرار، عدّاد `_errors` للقواطع، `_RATE`/`_SENT` تهدئة تيليجرام، `_alerted_ids` تنبيهات الصفقات، كاش التقويم `_cache`.

---

## 2. محرك الذكاء الاصطناعي وطاقم التحليل (AI Crew & MCP Protocols)

### 2.1 مسار الاستدعاء الدقيق (`run_crew` في `backend/app/services/crew.py`)

لا توجد تسميات مراحل معلّبة في الواجهة. كل فكرة وأداة ومناظرة تُبث لحظة حدوثها عبر SSE (`POST /api/agent/chat/stream`).

الترتيب الحتمي داخل `_run_crew_body`:

```
raise_if_paused + raise_if_cancelled
        │
        ▼
get_past_context(symbol, query=message)  → حدث agent_memory_recall
        │
        ▼
آخر 8 رسائل من agent_sessions.state.messages
        │
        ▼
إن لم تكن الرسالة سؤالاً سريعاً (is_quick_question):
    capture_chart_screenshot(symbol, gran, 180) إجباراً
    أحداث agent_tool_call / agent_tool_result بمعرّف vision-forced
        │
        ▼
1) TechnicalAgent     run_agent_turn + صورة PNG
2) FundamentalAgent   run_agent_turn (النص التقني حتى 4000 حرف)
3) مناظرة Bull / Bear  _run_debate — بلا أدوات
4) RiskManagerAgent   run_agent_turn
        │
        ▼
إن وُجد TradeRecommendation:
    persist_recommendation → enforce_risk_gate → save_recommendation
    store_decision (kind=risk, status=pending)
    أحداث agent_recommendation + recommendation
وإلا: AgentUnavailable
```

حدود المناظرة (`DebateBudget` في `run_control.py`):

- `DEBATE_MAX_ROUNDS = 2` — كل جولة = نطق ثور ثم نطق دب، أي حتى **4** نطوقات.
- `DEBATE_MAX_SECONDS = 90`.
- الشرط: `calls < max_rounds * 2` و`monotonic < deadline`.
- الثور والدب يستخدمان `_stream_plain` (Messages API بلا أدوات، `max_tokens=2048`).

إلغاء الجولة: `POST /api/agent/chat/stream/cancel` يضيف `run_id` إلى مجموعة `_cancelled`. عند إغلاق تيار SSE يُستدعى `request_cancel` تلقائياً.

### 2.2 أدوار الوكلاء ونصوص النظام

| الوكيل | المتغيّر | الأدوات المذكورة في النص | المخرج المتوقع |
|---|---|---|---|
| TechnicalAgent | `TECHNICAL_SYSTEM` = `SYSTEM_PROMPT` + تعليمات ICT | `get_candles`, `calculate_ict_levels`, `structure_scan`, `capture_chart_screenshot`, `draw_on_chart`, `query_technical_memory`, `list_strategies`, `propose_strategy` | موجز تقني فقط. **ممنوع** إصدار JSON توصية نهائي. |
| FundamentalAgent | `FUNDAMENTAL_SYSTEM` | `get_economic_calendar`, `get_market_sentiment`, `fetch_financial_news`, `query_macro_memory` | موجز كلّي. إن كانت `events[]` فارغة يجب التصريح بذلك. بلا توصية. |
| BullResearcher | `BULL_SYSTEM` | لا أدوات | 4–8 جمل مع الثور. |
| BearResearcher | `BEAR_SYSTEM` | لا أدوات | 4–8 جمل ضد الثور. |
| RiskManagerAgent | `RISK_SYSTEM` = `SYSTEM_PROMPT` + حكم نهائي | يُطلب منه `validate_risk_rules` ثم `send_recommendation` عند الموافقة | إما JSON `TradeRecommendation` مطابق للعقد، أو رفض صريح. |

`SYSTEM_PROMPT` في `backend/app/services/agent.py` يفرض مساراً متعدد الأطر (D/H4 ثم H1/M15 ثم M5/M1)، عقد JSON واحد بلا سياج markdown، حد R:R أدنى 1:2، وتفضيل أوامر LIMIT عند توازن FVG/OB. يُلحق به `ARTIFACT_PROTOCOL` لوثائق `<antArtifact>`.

**تعارض موثَّق:** جملة `SYSTEM_PROMPT` تقول إن الاستراتيجية «تصبح حيّة بعد تجاوز الحدود». الشيفرة في `StrategyLibrary.validate` **لا تثبّت** (`pinned=False`, `status=validated`) وتتجاهل `auto_activate`. التثبيت يتم فقط عبر `approve` أو `pin` من المشغّل.

### 2.3 مساران للتنفيذ: SDK ثم Messages

`run_agent_turn`:

1. يحاول `_try_sdk_turn`: `ClaudeSDKClient` + خادم MCP اسمه `oanda` من `try_build_sdk_server()`. أدوات SDK تظهر للنموذج بالأسماء `mcp__oanda__*` كما في قائمة `SDK_TOOLS` داخل `sdk_runtime.py`.
2. إن فشل SDK بعلّة إعداد (`config`) أو `require_sdk=True` يُرفع `AgentUnavailable` بلا تراجع.
3. إن فشل بسبب نقل/معدل يُسجَّل `sdk_stats.record_fallback` ويُرجع `None` فيُستخدم Anthropic Messages:
   - حتى `max_rounds=8` جولات أداة.
   - تفكير مفعّل بميزانية 6000 رمز، و`max_tokens=12000`؛ عند الرفض يُعاد بلا تفكير و`max_tokens=8000`.
   - **قائمة الأدوات كاملة** `mcp_tool_specs()` لكل وكيل في مسار Messages. التقييد بالدور نصّي فقط، ليس تصفية بايثون.

قياس الرموز: `record_model_usage` يبث حدث `usage` ويُعرض في `ChatUsageMeter`.

### 2.4 قائمة أدوات MCP الحقيقية

المصدر الوحيد للتعاقد: `mcp_tool_specs()` و`dispatch_tool()` في `backend/app/services/mcp_tools.py`. خادم SDK يسجّل المجموعة نفسها عبر `create_sdk_mcp_server(name="oanda", version="1.0.0")`.

| الأداة | المدخلات المطلوبة | التنفيذ | المخرج |
|---|---|---|---|
| `get_candles` | `instrument`, `granularity`؛ `count` 1–5000 افتراضي 300 | `oanda.get_candles` | قائمة شموع `to_kline()` + `time` ISO + `complete` |
| `get_live_price` | `instrument` | `oanda.get_live_price` | `LivePrice` JSON: bid/ask/mid/spread/source/time |
| `capture_chart_screenshot` | `instrument`, `granularity`؛ `count` افتراضي 180؛ `overlays` اختياري | رسم matplotlib ثم PNG base64 | سلسلة base64. مسار SDK يعيد كتلة صورة. |
| `structure_scan` | `instrument`, `granularity`؛ `count` افتراضي 300 | `analyze_structure` ثم `structure_summary` | انحياز، BOS، عدد FVG/OB، كنس سيولة، التقاء |
| `calculate_ict_levels` | كالسابق | `calculate_ict_levels` | خريطة FVG وOB وسيولة الجلسة وفيبوناتشي |
| `send_recommendation` | `payload` (كائن `TradeRecommendation`) | `persist_recommendation` → بوابة المخاطر ثم SQLite ثم تيليجرام | `{ok, recommendation}` أو `{ok:false, rejected, reasons, gate}` |
| `validate_risk_rules` | `payload` أو حقول الإعداد مباشرة | `validate_risk_rules` | `{ok, actualRr, impliedRiskPercent, session, reasons, ...}` |
| `query_technical_memory` | `instrument`؛ `query` اختياري | `get_past_context` باستعلام افتراضي `"{instrument} ICT FVG order block"` | `{kind: technical, instrument, context}` |
| `query_macro_memory` | `instrument`؛ `query` اختياري | استعلام افتراضي `"{instrument} session calendar sentiment"` | `{kind: macro, instrument, context}` |
| `get_economic_calendar` | لا إلزام؛ افتراضي `XAU_USD`, `hours_ahead=24`, `min_impact=medium` | ساعة الجلسة + `upcoming_events` | أحداث حقيقية أو قائمة فارغة + `warning` عند الفشل |
| `get_market_sentiment` | `instrument` اختياري | شموع H1×120 + سعر حي | bias, lastBos, liquiditySweep, mid, spread, session |
| `fetch_financial_news` | `instrument` اختياري | RSS رويترز `feeds.reuters.com/reuters/businessNews` حتى 8 عناوين | `{ok, items}` أو `{ok:false, items:[], detail}` |
| `draw_on_chart` | `overlays` | يبث `agent_chart_overlays` مع `additive: true` | `{ok, overlays, additive}` |
| `propose_strategy` | `name` إلزامي وبقية عقد الاستراتيجية | `StrategyLibrary.propose(..., source=claude_proposed)` | مسودة `status=draft`, `pinned=false` |
| `validate_strategy` | `strategy_id` | `validate(..., days=730, auto_activate=False)` | `{ok, passed, reasons, strategy, report}` — لا تثبيت |
| `experiment_strategy` | حقول المسودة + `days` | حتى 8 باك تست؛ لا تثبيت | `{ok, job, strategy}` |
| `list_strategies` | `status` افتراضي `active` | المكتبة كاملة ثم تصفية الحالة؛ `all` يلغي التصفية | `{strategies: [...]}` |
| `record_post_trade_reflection` | `recommendation_id`, `outcome`؛ `pnl` افتراضي 0 | `write_reflection` | الدرس أو `{ok:false}` إن لم توجد ذكرى معلّقة |

أداة غير معروفة في `dispatch_tool` ترفع `ValueError("Unknown tool: …")`.

### 2.5 أوامر الشات في الواجهة (ليست طاقماً)

`frontend/src/lib/agentSend.ts` يعالج الاختصارات **قبل** استدعاء الطاقم:

| الأمر | السلوك |
|---|---|
| `/pair` أو `/symbol` | يغيّر رمز مساحة العمل فقط |
| `/timeframe` أو `/tf` | يغيّر الإطار |
| `/model` | يختار نموذجاً من الكتالوج |
| `/overlay clear` | يمسح الرسوم |
| `/scan` | `GET /api/structure` فقط — **لا طاقم** — ويرسم مستطيلات FVG |
| `/setup` | يستبدل النص بموجّه الإعداد الكامل ثم يبث الطاقم |

### 2.6 الذاكرة المعجمية (`backend/app/services/memory_log.py`)

ليست متجهات عصبية. التضمين:

1. `embed_text`: عدّاد رموز `[a-z0-9_]+` ثم تطبيع L2 → قاموس `{token: weight}`.
2. `cosine`: مجموع جداءات المفاتيح المشتركة.
3. `get_past_context(symbol, query, n_same=5, n_cross=3)` يقرأ **الحالات المحلولة فقط** (`include_pending=False`)، يرتّب بتشابه جيب التمام، ويأخذ حتى 5 دروس لنفس الرمز (قرار + انعكاس كامل) و3 دروس عبر الرموز (انعكاس أو أول 300 حرف من القرار).

دورة الحياة:

```
RiskManager يُنتج توصية
        → store_decision(kind=risk, status=pending, recommendation_id)
        → المشغّل يعلّم الحالة النهائية (HIT_TP1 / HIT_TP2 / STOPPED_OUT / EXPIRED / CANCELLED)
        → _reflection_loop كل 45ث يستدعي scan_closed_recommendations
        → write_reflection: إن وُجد مفتاح Anthropic يكتب Claude 2–4 جمل، وإلا deterministic_lesson
        → update_with_outcome يعيد حساب التضمين من القرار + الدرس + النتيجة
```

`query_technical_memory` و`query_macro_memory` يستدعيان الدالة نفسها مع استعلام مختلف فقط؛ لا يوجد جدولان منفصلان. الحقل `kind` على الصف (`technical | macro | risk`) يُستخدم عند التخزين لا عند الاسترجاع.

جلسات المحادثة تُحفظ في `agent_sessions.payload` كأحداث (`message`, `tool`, `debate`, `recall`, `recommendation`). الطاقم يحقن آخر 8 رسائل كنص خام في موجّه TechnicalAgent.

---

## 3. بوابة المخاطر وقواعد التداول الحتمية (Deterministic Risk Engine)

### 3.1 العقد والصيغ (`backend/app/services/risk_rules.py`)

الإعدادات الحاكمة من `SettingsPayload` بعد فك التشفير، مع افتراضات البيئة:

- `maxRiskPercent` افتراضي **1.0**
- `minRiskReward` افتراضي **2.0**
- `allowedSessions` افتراضي `["london", "ny", "asian"]`

**نسبة المخاطرة الضمنية** — ليست مخاطرة حساب وسيط:

```
إن riskPercent صريح > 0  →  استخدمه
وإلا إن entry ≠ 0        →  |entry − SL| / |entry| × 100
وإلا                     →  0
```

يُبحث `riskPercent` أولاً داخل `tradeSetup` ثم في جذر الحمولة.

**R:R:**

```
إن riskRewardRatio > 0  →  استخدمه
وإلا إن وُجدت takeProfitLevels و entry و SL:
    risk = |entry − SL|
    rr   = |آخر_TP − entry| / risk     إن risk ≠ 0
```

**الجلسة UTC** من `macro_feed.current_session`:

| ساعة UTC | الاسم |
|---|---|
| 0–6 | `asian` |
| 7–11 | `london` |
| 12–15 | `london_ny_overlap` |
| 16–20 | `ny` |
| 21–23 | `late_ny_asia` |

`_session_allowed`: التطابق الحرفي، أو `london_ny_overlap` إن وُجد `london` أو `ny` في القائمة، أو `late_ny_asia` إن وُجد `ny` أو `asian`.

`validate_risk_rules` يعيد:

```
ok = ok_rr AND sess_ok AND ok_risk
actualRr, impliedRiskPercent, minRiskReward, maxRiskPercent, session, sessionAllowed, reasons[]
```

`enforce_risk_gate` يستدعي التحقق ويرفع `RiskRejected(result)` إن `ok` خطأ.

### 3.2 أين تُفرض البوابة وأين لا تُفرض

| المسار | هل تُفرض؟ |
|---|---|
| `persist_recommendation` (أداة `send_recommendation` + نهاية الطاقم) | نعم دائماً |
| اعتماد إشارة الوارد `approve_signal` → `promote_signal` → `persist_recommendation` | نعم |
| قبول إشارة البوت `_accept` | نعم ثم `_bot_limits` التي **تضيّق فقط** (`botMinRr`, `botMaxRiskPercent`, `botAllowedSessions`) |
| `POST /api/bot/signals/{id}/to-recommendation` | يشترط `confidence ≥ 0.8` **ثم** `promote_signal` (البوابة). الوارد **لا** يشترط 0.8 |
| `PATCH /api/recommendations/{id}` → `update_recommendation` | **لا**. يدمج الحقول ويحفظ بلا بوابة |
| تعديل إشارة بعد الاعتماد | لا يعيد تشغيل البوابة |

البوت لا يتجاوز البوابة المقدّسة. حدود البوت إضافية.

### 3.3 عقد الاستراتيجية (DSL)

`backend/app/services/trading_bot/strategy_schema.py`:

```
SESSIONS = asia | london | ny | london_ny_overlap | london_close
TRIGGERS = liquidity_sweep | range_break | fvg | bos | ob_reject | news_candle
WAREHOUSE_TFS = M15 | H1 | H4 | D
```

تحويل الأعلام ↔ المحفّزات:

| علم `entry_conditions` | محفّز DSL |
|---|---|
| `asian_sweep` | `liquidity_sweep` |
| `breakout` | `range_break` |
| `fvg_exists` | `fvg` |
| `bos_confirmed` | `bos` |
| `reversal` | `ob_reject` |

`dsl_from_flags` يبني `{sessions, triggers, conditions}`. إن لم يُشعل أي علم فالمحرك الافتراضي `["fvg"]`. `sanitize_sessions` يقبل aliases: `asian→asia`, `london-ny/overlap→london_ny_overlap`. إن خلت القائمة تُستخدم كل الجلسات.

نموذج `StrategyRule`: `id, name, description, timeframes, direction∈{buy,sell,both}, entry_conditions, sessions, dsl, pinned, stop_rule, tp1_r=1.5, tp2_r=3.0, max_holding_bars=48, source∈{builtin,claude_proposed,manual}, status∈{draft,validated,active,rejected,archived,experimenting}`.

المضمّنة (`BUILTIN_IDS`) تُثبَّت افتراضياً وحالتها `active`:

| المعرّف | الاسم العربي | الفكرة في `BUILTIN_META` |
|---|---|---|
| `gold_liquidity_sniper` | قناص سيولة الذهب | كنس سيولة آسيا ثم ارتداد من FVG |
| `gold_breakout` | كسر نطاق الذهب | كسر نطاق آسيا مع إعادة اختبار |
| `gold_trend_follow` | تتبع اتجاه الذهب | الدخول مع اتجاه H4 عند FVG/OB |
| `gold_reversal` | انعكاس الذهب | انعكاس عند مناطق عرض/طلب |
| `gold_scalp` | سكالبينج الذهب | صفقات سريعة بوقف ضيق |

حدود الاعتماد `VALIDATION_THRESHOLDS`:

- `min_win_rate = 0.55`
- `min_profit_factor = 1.5`
- `min_total_trades = 50`
- `max_drawdown_r = 15.0`
- `min_total_r = 10.0`

### 3.4 كيف تتحول الشروط إلى أوامر فحص

في الباك تست (`backend/app/services/backtest/engine.py`):

1. نافذة شموع من المستودع فقط (`load_warehouse_window`). أطر غير `M15/H1/H4/D` ترفع `ValueError`.
2. لكل شمعة بعد `LOOKBACK`: `analyze_structure(window)` ثم `evaluate_rule` ثم `conditions_ok`.
3. `conditions_ok` يفهم أعلاماً أو DSL عبر `flags_from_dsl`، ثم يفحص **ثلاثة أعلام فقط**:
   - `asian_sweep` يتطلب `report.liquidity_sweep`
   - `fvg_exists` يتطلب `report.fvgs` غير فارغ
   - `bos_confirmed` يتطلب `report.last_bos`
4. أعلام `breakout` و`reversal` **لا تُفحص** هنا رغم وجودها في `FLAG_TO_TRIGGER`.
5. التنفيذ: سعر افتتاح الشمعة التالية ± `SLIPPAGE = 0.2`. تكلفة السبريد `SPREAD_COST = 0.35` تُخصم من R المحققة. أهداف `r_targets(fill, stop, side, tp1_r, tp2_r)`. أقصى احتفاظ `max_holding_bars`.

البوت الحي (`MultiStrategyAgent` ورفاقه) يولّد إشارات من المسح اللحظي ثم يمرّ عبر `_accept`؛ لا يستخدم محرك الباك تست في الدورة الحية.

### 3.5 دورة حياة الاستراتيجية

```
propose()                → draft, pinned=false
        │
        ├─ experiment_strategy (حتى 8 محاولات)
        │     status = experimenting أثناء الفشل
        │     إن نجح التحقق: awaiting_pin على الوظيفة، strategy=validated, pinned=false
        │     إن استُنفدت المحاولات: job.status = exhausted
        │
        └─ validate()    → إن نجح: validated + pinned=false
                           إن فشل: rejected + rejection_reason
                           auto_activate يُتجاهل صراحةً  (_ = auto_activate)

approve() أو pin(true)   → active + pinned=true   (KV strategy_pins)
unpin / pin(false)       → يُزال من get_active_strategies
reject()                 → rejected  (المضمّنة ممنوعة)
archive()                → archived  (المضمّنة ممنوعة)
delete()                 → المسودات فقط

المضمّنة: لا تُعدَّل ولا تُحذف. pin يتحكم في ظهورها:
  pinned=true  → status=active
  pinned=false → status=archived
```

`get_active_strategies` يعيد ما كان `pinned and status == active`. منسّق البوت يمسح:

- المضمّنة إن كانت نشطة **و** موجودة في `botActiveStrategies` (أو كل المضمّنة إن خلت القائمة)،
- **وكل** استراتيجية غير مضمّنة نشطة ومثبّتة، حتى إن لم تُذكر في الإعدادات.

تثبيت المشغّل يُحفظ في KV `strategy_pins`. المضمّنة تُعتبر مثبّتة إن غاب المفتاح.

وظائف التجربة `_JOBS` في الذاكرة. بعد إعادة التشغيل تختفي الوظائف لكن صف الاستراتيجية يبقى في جدول `strategies`.

---

## 4. محرك البيانات والسوق (Market Data, Repository & Scans)

### 4.1 OANDA مقابل المحاكي والانتقال

`Settings.oanda_configured` = وجود `oanda_api_token` و`oanda_account_id` معاً.

| البيئة | REST | Stream |
|---|---|---|
| `practice` (افتراضي) | `https://api-fxpractice.oanda.com` | `https://stream-fxpractice.oanda.com` |
| `live` | `https://api-fxtrade.oanda.com` | `https://stream-fxtrade.oanda.com` |

الرؤوس: `Authorization: Bearer …`, `Accept-Datetime-Format: RFC3339`.

`OandaClient.get_candles`:

1. إن `uses_warehouse(instrument, gran)` أي `XAU_USD` وأحد `M15/H1/H4/D`: اقرأ من المستودع عبر `read_gold_candles` (يجلب النواقص فقط).
2. وإلا `fetch_remote_candles` — صفحة واحدة حدها 5000 (حد v20).
3. عند أي فشل: `generate_candles` من المحاكي ثم `simulator.apply_close`.

`get_live_price`: REST `/v3/accounts/{id}/pricing`؛ عند الفشل أو غياب الإعداد: `simulator.tick`.

`stream_prices`: GET مطوّل `/v3/accounts/{id}/pricing/stream?instruments=…`. إن لم يُضبط OANDA فالدالة تعود فوراً (مولّد فارغ) و`price_pump` ينتقل إلى تكات المحاكي.

المحاكي (`backend/app/services/simulator.py`): عشرة أزواج في `INSTRUMENT_SPECS`، ذهب افتراضي 2654.20، بذرة عشوائية ثابتة للتكات. السبريد = `pip * 1.2` للذهب وإلا `0.8`.

الانتقال «السلس»: أي مسار حي (شموع، سعر، بث) يسقط إلى المحاكي عند غياب الاعتماد أو خطأ HTTP، ويُسجَّل تحذير في السجل. المستودع يكتب `source=oanda` أو `source=simulator` حسب الإعداد وقت المزامنة.

### 4.2 مستودع الشموع

ثوابت `gold_warehouse.py`:

| الثابت | القيمة |
|---|---|
| `GOLD_SYMBOL` | `XAU_USD` |
| `WAREHOUSE_TFS` | `M15`, `H1`, `H4`, `D` |
| `RETENTION_DAYS` | 730 |
| `BATCH_SIZE` | 5000 |
| `BATCH_DELAY_SEC` | 0.4 |
| `STALE_GRACE_SEC` | 120 |
| `SYNC_INTERVAL_SEC` | M15=900، H1=3600، H4=14400، D=86400 |

الركود: `age > 2 × interval + 120`. مثال M15: أقدم من 1920 ثانية تُعد راكدة. فجوات عطلة نهاية الأسبوع تُعلَّم `weekend=true` ولا تُحسب «غير متوقعة».

`read_gold_candles` عند الطلب: إن نقص العدد يجلب أقدم؛ إن كانت أحدث شمعة أقدم من فترتين يجلب الأحدث. يُدرَج الكامل فقط (`complete is not False`).

تقدير الحجم: ≈ 220 بايت/صف × عدد صفوف أسبوع التداول (5/7).

### 4.3 المسح الدوري والقواطع

دورة البوت `run_cycle` بالترتيب إن لم يكن Pause ولا Safe Mode:

1. `news_candle` — `NewsCandleAgent.monitor_events()`
2. `multi_strategy` — `MultiStrategyAgent.scan_xau_usd()` على الاستراتيجيات النشطة
3. `pattern_notes` — `PatternNotesAgent.detect_patterns()`

كل إشارة تمر `_accept`: Pause / Safe Mode / `is_halted(strategyId)` → بوابة المخاطر → `_bot_limits` → `save_signal` → `schedule_bot_signal`. ثم `record_scan` حتى لو صُفر القبول.

القواطع (`backend/app/services/trading_bot/circuit.py`):

| الآلية | التخزين | العتبة | الأثر |
|---|---|---|---|
| سلسلة خسائر لكل استراتيجية | KV `strategy_circuits` JSON | `LOSS_LIMIT = 4` | `halted=true`، `_accept` يرفض |
| أخطاء مسح متتالية | عدّاد عملية `_errors` | `ERROR_LIMIT = 5` | `desk_safe_mode = "1"` يوقف كل الاستراتيجيات |
| الوضع الآمن اليدوي/التلقائي | KV `desk_safe_mode` | القيمة `"1"` | `is_halted` يعيد True لكل المعرّفات |
| Pause اليدوي | KV `system_paused` | `"1"/"true"/"yes"/"on"` | يغلب الجميع |

`note_outcome(won=True)` يصفّر سلسلة الخسائر. `resume_strategy` يصفّر `halted` و`losses`. عدّاد الأخطاء **لا يُكتب إلى القرص**؛ إعادة التشغيل تصفّره بينما يبقى Safe Mode إن كُتب إلى KV.

Preflight (`backend/app/services/preflight.py`): أربعة فحوص. **Pause وحده حاجز** (`blocking=True`). المستودع الراكد وتغذية OANDA وآخر خطأ المسح معلوماتية فقط.

### 4.4 التقويم والأخبار

`economic_calendar.py`:

- المصدر الافتراضي Forex Factory: `https://www.forexfactory.com/calendar`.
- يُصفَّى USD + قائمة مراقبة (NFP, CPI, FOMC, GDP, claims, PMI, …).
- الفشل يعيد قائمة فارغة — لا أحداث مختلقة.
- TTL الكاش: `max(60, economicCalendarCacheTtl * 60)` ثانية. الحقل الافتراضي `5` → **300 ثانية**.
- `gold_impact` يُشتق من عناوين القوة/الضعف، ليس من رقم مطبوع مختلق.

`fetch_financial_news`: رويترز فقط؛ عند السقوط `{ok:false, items:[]}`.

---

## 5. واجهة المشغّل وتجربة المستخدم (Operator UX & UI Workflows)

### 5.1 شجرة المسارات

Next.js 14 مجموعة `(desk)` ملفوفة بـ `AuthGate` + `DeskLayout`. `/` يعيد التوجيه إلى `/agents`. `/bot` يعيد التوجيه إلى `/bots`.

| المسار | الغرض | متجر Zustand الأساسي |
|---|---|---|
| `/login` | كلمة المشغّل → كوكي JWT | — |
| `/agents`, `/agents/[sessionId]` | الدردشة + الرسم + الآثار | `useChat`, `useSessions`, `useWorkspace` |
| `/inbox`, `/inbox/[id]` | الوارد / الاعتمادات / التنبيهات | `useInbox` |
| `/bots` | مكتب البوت (وكلاء، إشارات، preflight) | `useBot` |
| `/bots/structure`, `/bots/patterns`, `/bots/news` | صفحات فرعية للوكلاء | `useBot` |
| `/scans`, `/scans/[id]` | دورات المسح | — (جلب REST) |
| `/briefing` | إحاطة ما قبل لندن | — |
| `/journal` | دفتر القرار | — |
| `/backtest` | تشغيل ومقارنة تقارير | `useBacktest` |
| `/strategy-lab`, `/strategy-lab/jobs/[id]` | المكتبة والتجارب | `useStrategyLab` |
| `/recommendations` | التوصيات وتشريح ما بعد الصفقة | `useRecommendations` |
| `/memory` | سجل الذاكرة | — |
| `/calendar` | التقويم الاقتصادي | `useCalendar` |
| `/settings` | الأسرار والحدود واللغة | `useSettings`, `useLocale` |

متاجر إضافية: `useUi` (الشريط الجانبي)، `useCatalog` (النماذج)، `useWorkspace` (الرمز والإطار والسعر والأوامر الرسومية).

اللغة الافتراضية `DEFAULT_LOCALE = "ar"` اتجاه `rtl`، مفتاح التخزين `foxagent_locale`. `applyDocumentLocale` يضبط `dir` و`lang` على `document`.

الشريط في `Sidebar.tsx` يعرض عدّاد الوارد المفتوح إن `counts.open > 0` (يظهر `9+` فوق 9).

قاعدة انتقاء Zustand: لا تُستخدم `|| []` / `|| {}` داخل المحدِّدات (تفادي React #185). المخازن تُعرِّف ثوابت فارغة مستقرة مثل `EMPTY_COUNTS`.

### 5.2 مسار اعتماد التوصية من الوارد إلى التنفيذ اليدوي

```
بوت / طاقم
   │
   ├─ إشارة bot_signals status∈{pending,staged}  → تبويب approvals
   └─ توصية recommendations status∈{PENDING,pending} بلا تسمية → تبويب inbox
                    │
                    ▼
GET /api/inbox  → InboxList
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
   اعتماد إشارة   رفض بسبب   ack للتنبيهات/الوارد
POST /approvals/{id}/approve
         │
         ▼
promote_signal → persist_recommendation (بوابة المخاطر)
         │
         ▼
signal.status = active + recommendationId
recommendation.status = PENDING تُعرض في /recommendations
         │
         ▼
المشغّل ينفّذ يدوياً لدى الوسيط
ثم PATCH الحالة (HIT_TP* / STOPPED_OUT / …)
ثم اختياري: POST-mortem عبر /recommendations/{id}/postmortem
         │
         ▼
حلقة الانعكاس تكتب الدرس في memory_entries
```

`ApprovalCard` يعرض الدخول والوقف وR والثقة. الرفض بلا نص يفشل في الخادم (`Rejection reason is required`). التنبيهات (مستودع راكد، خبر ≤30 دقيقة، خطأ بوت) تُغلق بـ ack ويُحفظ المعرّف في KV `inbox_acks`.

**التنفيذ اليدوي:** لا يوجد زر «أرسل إلى OANDA». النظام يتوقف عند التوصية/الإشارة المعتمدة. التنفيذ خارج FoxAgent.

الترويج عبر REST `/bot/signals/{id}/to-recommendation` يشترط ثقة ≥ 0.8. مسار الوارد لا يشترط ذلك، لكنه يمر بالبوابة نفسها.

### 5.3 الرسوم على klinecharts والتحديث الحي

عقد `KlineOverlay` في `schemas.py`: الأسماء `rect | trendLine | fibonacci | priceLine | textAnnotation | segment | fibonacciLine | simpleAnnotation | horizontalStraightLine | rayLine`. النقاط `{timestamp ms, value}`.

`frontend/src/lib/overlays.ts` — `NAME_MAP`:

| اسم العقد | نوع klinecharts |
|---|---|
| `trendLine` | `segment` |
| `rect` | `rect` |
| `fibonacci` / `fibonacciLine` | `fibonacciLine` |
| `priceLine` | `priceLine` (متقطع) |
| `textAnnotation` / `simpleAnnotation` | `simpleAnnotation` |
| الباقي | يُمرَّر كما هو |

`applyOverlays` ينشئ كل طبقة مع تأخير حركي 140 مللي ثانية. `focusTimestamp` يمرّر إلى أقرب شمعة و`scrollToDataIndex(..., 280)`.

مسارات الرسم:

1. توصية نهائية: `agentSend` يستدعي `applyToChart(rec.klineOverlays, focusTimestamp, rec.id)` — يستبدل الطبقات (`command.type=apply`).
2. أثناء التحليل: حدث SSE `agent_chart_overlays` → `appendToChart` (تراكمي، لا يمسح التوصية النهائية حسب وصف الأداة).
3. `/scan`: مستطيلات FVG من `structure_scan`.
4. استعادة الجلسة: `useSessions` يعيد تطبيق الطبقات المحفوظة.

التحديث السعري الحي:

- `DeskLayout` يفتح `WebSocket(wsUrl("/ws/market"))` ويكتب في `useWorkspace.prices`.
- إن انقطع الوصل: استطلاع REST كل **900 مللي ثانية**.
- `ChartCanvas` عند تغيّر `prices[symbol]` يعدّل إغلاق/أعلى/أدنى **آخر شمعة** عبر `chart.updateData` دون تغيير الطابع الزمني.
- إعادة تحميل التاريخ: `GET /api/candles` بـ 400 شمعة عند تغيّر الرمز أو الإطار أو `chartNonce`.

مؤشرات الإقلاع: MA على شموع، VOL، MACD. النمط `DARK_CHART_STYLES`.

`BotDesk` ما يزال يستطلع الحالة كل **15 ثانية** رغم وجود `/ws/bot` الذي يبث `scan_complete`.

---

## 6. مسارات الطوارئ والأمان (Security, Telegram & Emergency Ops)

### 6.1 زر Pause — الأثر اللحظي

المسار: `POST /api/system/pause` → `set_paused(True)`:

1. يضع `_paused_memory = True`.
2. يكتب KV `system_paused = "1"`.
3. يستدعي `coordinator.on_pause_changed(True)` الذي **يوقف** حلقة البوت (`is_running=False` ويلغي `_monitor_loop`).

`POST /api/system/resume` يعكس القيمة ويستأنف البوت فقط إن `botEnabled`.

ما يتوقف فوراً أو في أول فحص تالٍ:

| المكوّن | السلوك عند Pause |
|---|---|
| طاقم Claude | `raise_if_paused()` في أول `run_crew` → لا جولة |
| `price_pump` | لا تكات ولا استهلاك تيار OANDA |
| `gold_sync_loop` | تتخطى المزامنة |
| `_reflection_loop` | تتخطى الكتابة |
| `_ops_loop` | لا إحاطة ولا تنبيهات |
| قبول إشارات البوت | `_accept` يعيد `None` |
| `validate` / `start_experiment` | `{paused: true}` |
| Preflight | الفحص `pause` يصبح حاجزاً |

ما **لا** يتوقف: خادم HTTP نفسه، المصادقة، قراءة REST، WebSocket المفتوح (بلا تكات جديدة). الإلغاء الداخلي للجولة (`_cancelled`) مستقل عن Pause.

واجهة الحالة: `GET /api/system/status` → `{paused}` و`desk_status.paused` في الوارد.

### 6.2 تيليجرام: الصادر والمسموح والوارد

**الصادر فقط** في الشيفرة: `sendMessage` و`sendPhoto` عبر `https://api.telegram.org` مع إعادة محاولة حتى 3 مرات عند 429/5xx أو خطأ نقل. لا يوجد `getUpdates` ولا تسجيل webhook في المستودع.

التفعيل يتطلب الثلاثة: `enableTelegramNotifications` و`telegramBotToken` و`telegramChatId` غير فارغ. `parse_chat_ids` يقبل فواصل `,;` أو أسطر.

أنواع الإرسال:

- تنبيه توصية HTML (`format_trade_alert_html`) مع صورة رسم اختيارية، حد تعليق 1024 وحد رسالة 4096.
- إشارة بوت / نتيجة بوت عبر `schedule_bot_signal` و`schedule_bot_result`.
- تشغيل: إحاطة، مستودع راكد، خبر، مع تهدئة:

| النوع | التهدئة |
|---|---|
| `briefing` | 6 ساعات |
| `stale` | 1800 ثانية |
| `news` | 1200 ثانية |
| `scan` | 900 ثانية |
| `circuit` | 900 ثانية |
| `signal` | 120 ثانية |

`_SENT` يمنع تكرار نفس المفتاح؛ إن تجاوز 400 عنصراً يُصفَّر.

**أوامر واردة** عبر `POST /api/telegram/commands` الجسم `{text, chatId|chat_id}` — يستدعي `handle_command`:

| الأمر | الشرط | الأثر |
|---|---|---|
| `/pause` | `chat_id` ضمن قائمة `telegramChatId` | `set_paused(True)` |
| `/resume` | كذلك | `set_paused(False)` |
| `/status` أو `/inbox` | كذلك | يعيد `desk_status` + رابط `https://foxagent.lork.cloud/inbox` |
| أي أمر آخر | — | `{ok:false, detail: unknown command}` |
| دردشة غير مدرجة | — | `{ok:false, detail: chat not allow-listed}` |

عزل المشغّل الواحد: JWT `sub=operator` بلا أدوار متعددة. أوامر تيليجرام لا تُنفَّذ إلا لمعرّفات الدردشة المخزّنة. **لا يوجد مستمع داخل العملية**؛ يجب أن يستدعي مسار `/api/telegram/commands` وكيل خارجي (webhook أو سكربت) وإلا الأوامر لا تصل.

### 6.3 النسخ الاحتياطي والاستعادة

السكربت `scripts/backup_foxagent.sh`:

```
DATA_DIR="${FOXAGENT_DATA_DIR:-/opt/foxagent/data}"
ينسخ foxagent.db و.foxagent.key إلى $DATA_DIR/backups بطابع UTC
Pause غير مطلوب
```

في Docker الإنتاجي القاعدة داخل الحجم `foxagent_data` الموصول على `/data` داخل الحاوية (`FOXAGENT_DATA_DIR=/data`). المسار الافتراضي `/opt/foxagent/data` على المضيف **قد لا يحتوي** الملف الحي ما لم يُضبط المتغيّر ليطابق نقطة الوصل الفعلية للحجم.

الاستعادة اليدوية:

1. أوقف المكدس (`docker compose -p foxagent stop`) لتفادي قفل WAL.
2. انسخ `foxagent-*.db` إلى مسار `foxagent.db` الذي تراه الحاوية (`/data/foxagent.db`).
3. انسخ ملف `.foxagent.key` المطابق لنفس النسخة (بدونه تفشل قراءة `runtime_settings` المشفّرة ما لم يُضبط `SETTINGS_SECRET` نفسه).
4. أعد التشغيل. `create_all` لا يحذف الجداول الموجودة.

لا توجد أداة استعادة تلقائية في الواجهة.

### 6.4 سطح الهجوم المختصر

- سر JWT الاحتياطي ثابت في المستودع إن لم يُضبط `JWT_SECRET`.
- حد المعدل لكل عملية، يُصفَّر عند تعدد العمال.
- `/api/health` يكشف وضع البيانات وصحة المفتاح وجاهزية المستودع **بعد المصادقة**.
- كوكي `SameSite=lax` مناسب لنفس الموقع عبر Caddy؛ لا `Secure` في `set_auth_cookie` (يعتمد على إنهاء TLS أمام الحاوية).
- أسرار OANDA/Anthropic/Telegram لا تُعاد في `SettingsPublic`.

---

## 7. الثغرات المرصودة وتوصيات الترقية الفنية

كل بند مستخرج من قراءة الشيفرة أعلاه، مع خطوة تصحيح مقترحة.

### 7.1 بوابة المخاطر لا تُعاد عند التعديل

`update_recommendation` يدمج أي رقعة ويحفظ. مشغّل أو عميل يمكنه خفض R:R أو توسيع الوقف بعد اجتياز البوابة.

**تصحيح:** استدعِ `enforce_risk_gate` داخل `update_recommendation` عندما تُلمس حقول `tradeSetup` أو `riskPercent`. ارفض الرقعة بـ 400 و`RiskRejected.reasons`.

### 7.2 مخاطرة هندسية ≠ مخاطرة حساب

`implied_risk_percent` هي `|entry−SL|/entry*100`. عند ذهب ~2650 ووقف 10 دولارات تُحسب ≈ 0.38٪ من السعر لا من رصيد الحساب. الحد `maxRiskPercent=1` لا يحمي حجم العقد.

**تصحيح:** أدخل `accountEquity` و`units` أو `riskAmount` في `TradeSetup`، واحسب المخاطرة كـ `|entry−SL| × units / equity`. أبقِ الصيغة الهندسية كفحص ثانوي لانزلاق الوقف.

### 7.3 `conditions_ok` ناقص مقابل عقد DSL

أعلام `breakout` و`reversal` تُحفظ وتُحوَّر في التجارب (المحاولات 5 و7) لكن محرك الباك تست لا يرفض عند غياب كسر النطاق أو رفض OB.

**تصحيح:** أضف فحوصاً مقابلة لحقول `StructureReport` (كنس/كسر نطاق آسيا، رفض منطقة العرض/الطلب) أو ارفع خطأ تحقق عند حفظ استراتيجية تعتمد أعلاماً غير منفَّذة.

### 7.4 تعارض ثقة 0.8 بين مسارين

الوارد يعتمد أي إشارة `pending/staged` عبر البوابة. REST `/to-recommendation` يرفض تحت 0.8.

**تصحيح:** عتبة واحدة في `promote_signal` أو إزالة عتبة REST إن كان الاعتماد البشري كافياً. وثّق القرار في الواجهة.

### 7.5 حالة متطايرة تُفقد عند إعادة التشغيل

`_SCANS`, `_JOBS`, `_ENTRIES` (ما عدا تشريح نُسخ إلى `recommendations.payload`), `_errors`, تهدئة تيليجرام، `_alerted_ids`. بعد إعادة التشغيل يختفي تاريخ المسح ووظائف المختبر وعدّاد أخطاء القاطع (بينما قد يبقى Safe Mode في KV).

**تصحيح:** جداول SQLite لـ scans/jobs/journal، وعدّاد أخطاء في KV بجانب `desk_safe_mode`.

### 7.6 كاتب SQLite واحد رغم WAL

كل الحلقات (مزامنة 60ث، بوت، انعكاس، إعدادات، توصيات) تكتب نفس الملف. `busy_timeout=30000` يخفف القفل ولا يلغيه. تجارب المختبر ذات 8 باك تست طويلة تحجز الكاتب.

**تصحيح:** صف كتابة واحد، أو Postgres عندما يتجاوز المستودع مئات الآلاف من الصفوف. لا تشغّل تجربة مختبر أثناء المزامنة الثقيلة الأولى.

### 7.7 إلغاء مهام lifespan بلا انتظار

عند الإيقاف تُلغى `pump/reflector/warehouse/ops` دون `await`. قد تُقطع كتابة WAL في منتصف المعاملة.

**تصحيح:**

```python
for t in (pump, reflector, warehouse, ops):
    t.cancel()
await asyncio.gather(pump, reflector, warehouse, ops, return_exceptions=True)
```

### 7.8 `/api/health` محمي بينما المراقبة تتوقع 200 عاماً

حد المعدل يتجاوز الصحة، والمصادقة لا تتجاوزها.

**تصحيح:** أضف `/api/health` إلى `PUBLIC_API_PATHS` وأعد نسخة مختصرة بلا تفاصيل المفتاح، أو اترك نسخة `/api/health/ready` عامة و`/api/health/detail` محمية.

### 7.9 سر JWT الاحتياطي وغياب `Secure` على الكوكي

`foxagent-dev-jwt-secret` في المستودع. الكوكي بلا `secure=True`.

**تصحيح:** ارفض الإقلاع إن خلا `JWT_SECRET` خارج التطوير. اضبط `secure=True` خلف TLS.

### 7.10 حد المعدل لكل عملية لا عبر العنقود

`RateLimitMiddleware.hits` في الذاكرة. عاملان = ضعف الميزانية.

**تصحيح:** إن وُجد Redis استخدم `INCR` بنوافذ زمنية؛ وإلا وثّق أن النشر عملية واحدة كما في compose الحالي.

### 7.11 أوامر تيليجرام بلا مستمع

`handle_command` جاهز لكن لا يوجد webhook ولا polling في المستودع.

**تصحيح:** سجّل webhook إلى `https://foxagent.lork.cloud/api/telegram/commands` مع تحقق سر، أو حلقة `getUpdates` داخل lifespan تحترم قائمة الدردشة. أبقِ العزل كما هو.

### 7.12 مسار النسخ الاحتياطي لا يطابق حجم Docker

السكربت يقرأ `/opt/foxagent/data` افتراضياً. القاعدة الحية في حجم اسمه `foxagent_data`.

**تصحيح:** اجعل السكربت ينفَّذ `docker compose cp` أو `docker run --volumes-from` / نقطة وصل موثّقة، أو صدّر `FOXAGENT_DATA_DIR` في وحدة systemd إلى مسار الحجم الفعلي. انسخ أيضاً `-wal` و`-shm` إن نُسخ الملف والمخدم يعمل.

### 7.13 إحاطة لندن مثبتة على UTC 07:00–07:19

`_ops_loop` يستخدم `now.hour == 7` بلا توقيت لندن الصيفي. بعد BST تصبح الإحاطة 08:00 لندن.

**تصحيح:** `ZoneInfo("Europe/London")` واستخدم الساعة المحلية 07:00–07:19.

### 7.14 BotDesk يستطلع كل 15 ثانية رغم `/ws/bot`

البث موجود (`bot_hub.broadcast` عند `scan_complete`). الواجهة لا تشترك.

**تصحيح:** وصّل `BotDesk` بـ `/ws/bot` وأبقِ الاستطلاع احتياطياً كما في `DeskLayout`.

### 7.15 `SYSTEM_PROMPT` يعد بحياة الاستراتيجية بعد العتبات

يخالف `validate` الذي لا يثبّت.

**تصحيح:** استبدل الجملة بـ: «التجاوز ينقل الحالة إلى validated؛ المشغّل وحده يثبّت».

### 7.16 وثائق قديمة تصف استطلاع REST للسعر

`price_pump` يستهلك تيار OANDA الرسمي. أي README يقول عكس ذلك مضلل.

**تصحيح:** اجعل هذه الوثيقة مصدر الحقيقة، وحدّث `docs/FOXAGENT_REFERENCE_AR.md` ليشير إليها.

### 7.17 زمن استجابة الطاقم

جولة كاملة = لقطة رسم إجبارية + Technical (حتى 8 جولات أداة) + Fundamental + حتى 4 نطوقات مناظرة خلال 90 ثانية + RiskManager. كل مسار SDK/Messages يبث التفكير. زمن الانتظار دقائق وليس ثوانياً. لا يوجد حد إجمالي للجولة سوى إلغاء SSE عند إغلاق الاتصال.

**تصحيح:** ميزانية زمنية شاملة (مثلاً 180 ثانية) تُلغي `run_id`؛ اجعل الأسئلة السريعة تتخطى المناظرة كما تتخطى اللقطة.

### 7.18 البوت لا يتداول لدى الوسيط — وهذا مقصود

لا ثغرة تنفيذ صامت. أي طلب «تفعيل تنفيذ آلي» يحتاج عقداً جديداً وبوابة مخاطر على الحجم الحقيقي ومسار Pause على طبقة الأوامر. لا يوجد ذلك في المستودع الحالي.

---

## ملحق أ — مسارات REST ذات الصلة بالتشغيل

بادئة كلها `/api` ما عدا WebSocket.

| الطريقة | المسار | ملاحظة من الكود |
|---|---|---|
| POST | `/auth/login` | عام + خارج حد المعدل |
| POST | `/auth/logout` | عام |
| GET | `/health` | يحتاج JWT |
| GET/PUT | `/settings` | التشفير عند الكتابة |
| POST | `/system/pause` `/system/resume` | KV + إيقاف البوت |
| POST | `/agent/chat/stream` | SSE الطاقم |
| GET | `/inbox` `/approvals` | تجميع الإشارات والتوصيات والتنبيهات |
| POST | `/approvals/{id}/approve` | ترويج + بوابة |
| GET | `/candles` `/prices` `/structure` | مستودع أو حي أو محاكٍ |
| GET | `/bot/preflight` | Pause حاجز وحيد |
| POST | `/bot/start` `/bot/stop` | يضبط `botEnabled` |
| POST | `/strategies/{id}/validate` | `auto_activate=False` |
| POST | `/strategies/{id}/approve` `/pin` | التثبيت البشري |
| POST | `/lab/experiments` | حتى 8 محاولات في الذاكرة |
| POST | `/telegram/commands` | أوامر القائمة البيضاء |
| GET | `/warehouse/gaps` | فجوات المستودع |

## ملحق ب — قواعد مقدّسة مستخرجة من السلوك لا من التعليقات التسويقية

1. `enforce_risk_gate` في بايثون قبل أي حفظ توصية عبر `persist_recommendation`.
2. Pause يوقف الطاقم وضخ السعر ومزامنة المستودع والإحاطات وحلقة البوت.
3. البوت لا يستدعي واجهة أوامر OANDA.
4. لا تنفيذ بايثون حر من النموذج؛ الأدوات مغلقة في `dispatch_tool`.
5. الأخبار والشموع الفارغة تبقى فارغة.
6. التثبيت البشري فقط — `auto_activate` يُتجاهل.
7. الواجهة عربية RTL أولاً.
8. الذهب وحده في المستودع والمختبر والبوت؛ أزواج المحاكي الأخرى للرسم الحي فقط.

## ملحق ج — خريطة الملفات المصدر

| المجال | المسار |
|---|---|
| إقلاع الخادم والوسائط والحلقات | `backend/app/main.py` |
| الإعدادات البيئية | `backend/app/config.py` |
| المصادقة | `backend/app/auth.py` |
| المسارات | `backend/app/api/routes.py` |
| البث السعري | `backend/app/api/ws.py` |
| الطاقم | `backend/app/services/crew.py` |
| الأدوات | `backend/app/services/mcp_tools.py` |
| المخاطر | `backend/app/services/risk_rules.py` |
| Pause | `backend/app/services/run_control.py` |
| المستودع والمزامنة | `backend/app/services/gold_warehouse.py`, `gold_sync.py` |
| OANDA | `backend/app/services/oanda.py` |
| البوت | `backend/app/services/trading_bot/coordinator.py` |
| DSL والمكتبة | `strategy_schema.py`, `strategy_library.py`, `experiment.py` |
| الوارد | `backend/app/services/inbox.py` |
| تيليجرام | `telegram_service.py`, `telegram_ops.py` |
| الواجهة | `frontend/src/app/(desk)/*`, `frontend/src/stores/*`, `frontend/src/lib/overlays.ts`, `frontend/src/lib/agentSend.ts` |
| النشر | `deploy/docker-compose.yml`, `deploy/Caddyfile` |

---

*نهاية المرجع. أي تعارض بين تعليق قديم وهذه الوثيقة يُحسم لصالح الشيفرة المشار إليها أعلاه.*
