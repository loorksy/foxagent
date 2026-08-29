# FoxAgent

Autonomous ICT / Smart Money trading workstation: **Claude Agent SDK** + **OANDA v20** + klinecharts 9.8 + FastAPI + Next.js.

The agent talks to Anthropic only. There is no local / algorithmic stand-in that fabricates a Claude setup. `ANTHROPIC_API_KEY` must be a real key that can create messages. Without it (or if Anthropic rejects the account), the chat returns the provider error.

Single-operator login is required. Set `APP_PASSWORD` (or a bcrypt `ADMIN_PASSWORD_HASH`) and `JWT_SECRET`. The UI sends an httpOnly cookie after `POST /api/auth/login`. Every `/api/*` route and `/ws/market` require that token.

## Stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js 14 App Router, Tailwind, Zustand, klinecharts 9.8 |
| Backend | FastAPI, SQLAlchemy (SQLite / Postgres), optional Redis pub/sub |
| Agent | Claude Agent SDK MCP tools → Anthropic Messages tool-use (same key, no fake fallback) |
| Market | OANDA REST candle + tick **polling** (about 0.85s) when credentials are set; deterministic simulator otherwise. `stream_prices` / `oanda_stream_base` exist in code but are **not wired** — REST poll is the live path. |
| Vision | Matplotlib chart snapshots passed into Claude Vision / tool results |

## Quick start

```bash
cp .env.example .env
# required for the agent: ANTHROPIC_API_KEY
# required for the UI: APP_PASSWORD (or ADMIN_PASSWORD_HASH) and JWT_SECRET
# optional market feed: OANDA_API_TOKEN, OANDA_ACCOUNT_ID

python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

cd frontend && npm install && cd ..

# terminal 1
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend

# terminal 2
cd frontend && npm run dev -- --hostname 0.0.0.0 --port 3000
```

Or `bash scripts/dev.sh`.

UI: http://localhost:3000 · login, then the desk. `GET /api/health` is auth-protected; it probes Anthropic with a live `messages.create` (cached ~2 minutes) and reports `anthropicReady` / `anthropicDetail` plus Claude Agent SDK path counters (`sdkPathSuccessCount`, `sdkPathFallbackCount`, `sdkPathSuccessRate`). Settings → Verify key uses the stored key when the form field is empty. UI copy lives in `frontend/src/i18n/messages/` (register another locale in `frontend/src/i18n/index.ts`).

Optional Postgres + Redis:

```bash
docker compose up -d
# DATABASE_URL=postgresql+asyncpg://foxagent:foxagent@localhost:5432/foxagent
# REDIS_URL=redis://localhost:6379/0
```

## Workstation

- Chat-first RTL console with chart side pane / mobile sheet
- Slash commands:
  - `/scan` — `GET /api/structure` only (no crew run); overlays unfilled FVGs
  - `/setup` — starts a crew run with a dedicated setup prompt
  - `/timeframe 15m`, `/model sonnet`, `/pair xauusd`, `/overlay clear`
- klinecharts canvas with polled ticks, MA / VOL / MACD, ICT overlays (`rect`, `trendLine`, `fibonacci`, `priceLine`, `textAnnotation`)
- Top-bar Refresh bumps `chartNonce` so `ChartCanvas` re-fetches candles
- Show on chart recenters at `focusTimestamp` and draws the setup
- Recommendations page with R:R, entry / SL / TP, confluence, status
- Memory / Insights page (`GET /api/memory` + `GET /api/memory/context`)
- Settings for Anthropic + OANDA + Telegram secrets (Fernet-encrypted at rest), risk rules, and a global Pause / Resume kill switch
- Telegram dispatcher: when a setup is saved, a background task sends an HTML alert plus an overlay chart snapshot. Disabled or missing secrets fail closed.

## Agent contract

MCP tools registered for Claude (13):

1. `get_candles(instrument, granularity, count)`
2. `get_live_price(instrument)`
3. `capture_chart_screenshot(instrument, granularity)`
4. `structure_scan(instrument, granularity)`
5. `send_recommendation(payload)` — persistence is risk-gated in code, not only by this tool
6. `calculate_ict_levels`
7. `query_technical_memory`
8. `get_economic_calendar`
9. `get_market_sentiment`
10. `fetch_financial_news`
11. `query_macro_memory`
12. `validate_risk_rules` — preview only; `persist_recommendation` still enforces the gate
13. `record_post_trade_reflection`

Recommendation JSON matches the `klineOverlays` overlay API consumed by the chart.

## Known limitations

- **Single-operator only.** One shared password/JWT. No multi-tenant accounts, roles, or per-user isolation.
- **SQLite by default.** Set `DATABASE_URL` to Postgres for shared/production persistence.
- **Lexical memory, not vector embeddings.** Recall uses token-count cosine similarity, not a vector database.
- **No OANDA streaming socket.** Prices are REST-polled (or simulated). The unused `stream_prices` helper is intentionally not connected.

## Tests

```bash
cd backend && PYTHONPATH=. ../backend/.venv/bin/pytest -q
```
