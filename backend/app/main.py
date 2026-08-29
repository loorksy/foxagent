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
    yield
    pump.cancel()
    reflector.cancel()
    warehouse.cancel()


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
