# FoxAgent

Autonomous ICT / Smart Money trading workstation: **Claude Agent SDK** + **OANDA v20** + **klinecharts-pro** (klinecharts 9.8 overlay engine) + FastAPI + Next.js.

The desk runs without credentials using a deterministic market simulator. Add `ANTHROPIC_API_KEY` and OANDA tokens in Settings to switch the agent and feed to live providers.

## Stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js 14 App Router, Tailwind, Zustand, klinecharts 9.8 / `@klinecharts/pro` |
| Backend | FastAPI, SQLAlchemy (SQLite / Postgres), optional Redis pub/sub |
| Agent | Claude Agent SDK MCP tools → Anthropic tool-use fallback → algorithmic ICT analyst |
| Market | OANDA REST candles + streaming prices, simulator fallback |
| Vision | Matplotlib chart snapshots passed into Claude Vision / tool results |

## Quick start

```bash
cp .env.example .env
# optional: ANTHROPIC_API_KEY, OANDA_API_TOKEN, OANDA_ACCOUNT_ID

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

Optional Postgres + Redis:

```bash
docker compose up -d
# DATABASE_URL=postgresql+asyncpg://foxagent:foxagent@localhost:5432/foxagent
# REDIS_URL=redis://localhost:6379/0
```

## Workstation

- **Split / Full Chart / Full Chat** view switcher in the agent header and top bar
- **Omnibar** with inline pair + Claude model badges, slash commands (`/scan`, `/timeframe 15m`, `/model sonnet`, `/pair xauusd`, `/overlay clear`)
- **klinecharts** canvas with live ticks, MA / VOL / MACD, animated ICT overlays (`rect`, `trendLine`, `fibonacci`, `priceLine`, `textAnnotation`)
- **View on Chart / Apply to Chart** recenters the candle at `focusTimestamp` and draws the setup
- **Recommendations ledger** with R:R, entry / SL / TP, confluence, status
- **Settings drawer** for Anthropic + OANDA + Telegram secrets (Fernet-encrypted at rest) and risk rules
- **Telegram dispatcher**: when a setup is saved, a background task sends an HTML alert plus an overlay chart snapshot (`sendPhoto`, caption ≤ 1024 chars). Disabled or missing secrets fail closed.

## Agent contract

MCP tools registered for Claude Agent SDK:

- `get_candles(instrument, granularity, count)`
- `get_live_price(instrument)`
- `capture_chart_screenshot(instrument, granularity)`
- `structure_scan(instrument, granularity)`
- `send_recommendation(payload)`

Recommendation JSON matches the `klineOverlays` overlay API consumed by the chart.

## Tests

```bash
cd backend && PYTHONPATH=. ../backend/.venv/bin/pytest -q
```

## Notes

klinecharts-pro does not expose the inner chart overlay API, so the workstation uses **klinecharts 9.8** (the Pro engine) with a custom Bloomberg-style chrome. Pro CSS / types remain available via `@klinecharts/pro`.
