from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.ws import router as ws_router, price_pump
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
    pump = asyncio.create_task(price_pump())
    reflector = asyncio.create_task(_reflection_loop())
    yield
    pump.cancel()
    reflector.cancel()


async def _reflection_loop() -> None:
    from app.services.reflection import scan_closed_recommendations

    await asyncio.sleep(8)
    while True:
        try:
            written = await scan_closed_recommendations()
            if written:
                logger.info("Post-trade reflections written: %s", written)
        except Exception as exc:
            logger.warning("Reflection scan failed: %s", exc)
        await asyncio.sleep(45)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    origins = settings.cors_origin_list
    wildcard = not origins or origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if wildcard else origins,
        allow_credentials=not wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)
    return app


app = create_app()
