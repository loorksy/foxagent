# FoxAgent

Autonomous ICT / Smart Money trading workstation: **Claude Agent SDK** + **OANDA v20** + klinecharts 9.8 + FastAPI + Next.js.

The agent talks to Anthropic only. There is no local / algorithmic stand-in that fabricates a Claude setup. `ANTHROPIC_API_KEY` must be a real key that can create messages. Without it (or if Anthropic rejects the account), the chat returns the provider error.

## Stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js 14 App Router, Tailwind, Zustand, klinecharts 9.8 |
| Backend | FastAPI, SQLAlchemy (SQLite / Postgres), optional Redis pub/sub |
| Agent | Claude Agent SDK MCP tools → Anthropic Messages tool-use (same key, no fake fallback) |
| Market | OANDA REST candles + streaming prices; deterministic simulator only when OANDA is unset |
| Vision | Matplotlib chart snapshots passed into Claude Vision / tool results |

## Quick start

```bash
cp .env.example .env
# required for the agent: ANTHROPIC_API_KEY
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

UI: http://localhost:3000 · API: http://localhost:8000/api/health

`GET /api/health` probes Anthropic with a live `messages.create` (cached ~2 minutes) and reports `anthropicReady` / `anthropicDetail`. Settings → «التحقق من المفتاح» uses the stored key when the form field is empty.

Optional Postgres + Redis:

```bash
docker compose up -d
# DATABASE_URL=postgresql+asyncpg://foxagent:foxagent@localhost:5432/foxagent
# REDIS_URL=redis://localhost:6379/0
```

## Workstation

- Chat-first RTL console with chart side pane / mobile sheet
- Slash commands (`/scan`, `/timeframe 15m`, `/model sonnet`, `/pair xauusd`, `/overlay clear`)
- klinecharts canvas with live ticks, MA / VOL / MACD, ICT overlays (`rect`, `trendLine`, `fibonacci`, `priceLine`, `textAnnotation`)
- **عرض على الشارت** recenters at `focusTimestamp` and draws the setup
- Recommendations page with R:R, entry / SL / TP, confluence, status
- Settings for Anthropic + OANDA + Telegram secrets (Fernet-encrypted at rest) and risk rules
- Telegram dispatcher: when a setup is saved, a background task sends an HTML alert plus an overlay chart snapshot. Disabled or missing secrets fail closed.

## Agent contract

MCP tools registered for Claude:

- `get_candles(instrument, granularity, count)`
- `get_live_price(instrument)`
- `capture_chart_screenshot(instrument, granularity)`
- `structure_scan(instrument, granularity)` — real candle structure for Claude, not a substitute agent
- `send_recommendation(payload)`

Recommendation JSON matches the `klineOverlays` overlay API consumed by the chart.

## Tests

```bash
cd backend && PYTHONPATH=. ../backend/.venv/bin/pytest -q
```
