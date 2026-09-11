from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.auth_routes import router as auth_router
from app.api.routes import router as api_router
from app.api.ws import router as ws_router, price_pump
from app.auth import PUBLIC_API_PATHS, extract_request_token, require_token
from app.bus import bus
from app.config import get_settings
from app.db import init_db
from app.services.settings_store import apply_runtime_to_env, load_runtime_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await init_db()
    await bus.connect()
    try:
        runtime = await load_runtime_settings()
        apply_runtime_to_env(runtime)
    except Exception as exc:
        logger.warning("Could not load runtime settings: %s", exc)
    from app.services.gold_sync import gold_sync_loop

    pump = asyncio.create_task(price_pump())
    reflector = asyncio.create_task(_reflection_loop())
    warehouse = asyncio.create_task(gold_sync_loop())
    from app.services.trading_bot import get_coordinator

    bot = get_coordinator()
    import os

    autostart = os.environ.get("FOXAGENT_BOT_AUTOSTART", "1").strip().lower() not in {"0", "false", "off", "no"}
    from app.services.trading_bot.instances import get_manager

    manager = get_manager()
    try:
        await manager.ensure_default()
    except Exception as exc:
        logger.warning("Bot instance migration skipped: %s", exc)
    if autostart:
        try:
            runtime = await load_runtime_settings()
            if getattr(runtime, "botEnabled", False) and not await is_paused_safe():
                await bot.start()
        except Exception as exc:
            logger.warning("Gold bot autostart skipped: %s", exc)
        try:
            if not await is_paused_safe():
                await manager.start_enabled()
        except Exception as exc:
            logger.warning("Bot instances autostart skipped: %s", exc)
    ops = asyncio.create_task(_ops_loop())
    yield
    await bot.stop()
    await manager.stop_all()
    pump.cancel()
    reflector.cancel()
    warehouse.cancel()
    ops.cancel()


async def is_paused_safe() -> bool:
    from app.services.run_control import is_paused

    try:
        return await is_paused()
    except Exception:
        return False


async def _reflection_loop() -> None:
    from app.services.reflection import scan_closed_recommendations
    from app.services.run_control import is_paused

    await asyncio.sleep(8)
    while True:
        try:
            if not await is_paused():
                written = await scan_closed_recommendations()
                if written:
                    logger.info("Post-trade reflections written: %s", written)
        except Exception as exc:
            logger.warning("Reflection scan failed: %s", exc)
        await asyncio.sleep(45)


async def _ops_loop() -> None:
    """Pre-London briefing plus stale/news ops alerts. Pause skips sends."""
    from datetime import datetime, timezone

    from app.services.run_control import is_paused
    from app.services.telegram_ops import maybe_alert_news, maybe_alert_stale, send_briefing

    await asyncio.sleep(20)
    while True:
        try:
            if not await is_paused():
                now = datetime.now(timezone.utc)
                if now.hour == 7 and now.minute < 20:
                    await send_briefing()
                from app.services.gold_warehouse import timeframe_health

                health = await timeframe_health()
                frames = health.get("timeframes") or {}
                stale = [tf for tf, row in frames.items() if (row or {}).get("stale")]
                await maybe_alert_stale(stale)
                from app.services.economic_calendar import upcoming_events

                live = await upcoming_events(hours_ahead=1, min_impact="high")
                for event in live.get("events") or []:
                    title = str(event.get("title") or "")
                    event_id = str(event.get("id") or title)
                    raw_ts = event.get("timestamp") or event.get("time")
                    minutes = 0
                    try:
                        if isinstance(raw_ts, str):
                            ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                            minutes = int((ts - now).total_seconds() / 60)
                    except Exception:
                        minutes = 0
                    if 0 < minutes <= 30 and title:
                        await maybe_alert_news(title, minutes, event_id)
        except Exception as exc:
            logger.warning("Ops loop failed: %s", exc)
        await asyncio.sleep(60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit: int = 180, window: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window
        self.hits: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path in {"/api/health", "/api/auth/login"}:
            return await call_next(request)
        import time

        now = time.time()
        ip = request.client.host if request.client else "local"
        bucket = [t for t in self.hits.get(ip, []) if now - t < self.window]
        if len(bucket) >= self.limit:
            return JSONResponse({"detail": "rate limited"}, status_code=429)
        bucket.append(now)
        self.hits[ip] = bucket
        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
            try:
                require_token(extract_request_token(request))
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    origins = settings.cors_origin_list
    wildcard = not origins or origins == ["*"]
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if wildcard else origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, prefix="/api")
    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)
    return app


app = create_app()
