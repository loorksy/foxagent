from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable, Awaitable

from app.config import get_settings

logger = logging.getLogger(__name__)

Listener = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """In-process pub/sub with optional Redis fan-out."""

    def __init__(self) -> None:
        self._listeners: dict[str, set[Listener]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._redis = None

    async def connect(self) -> None:
        settings = get_settings()
        if not settings.redis_url:
            return
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            asyncio.create_task(self._redis_reader())
            logger.info("Redis pub/sub connected")
        except Exception as exc:
            logger.warning("Redis unavailable, using in-memory bus: %s", exc)
            self._redis = None

    async def _redis_reader(self) -> None:
        if self._redis is None:
            return
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("foxagent:*")
        async for message in pubsub.listen():
            if message.get("type") not in {"pmessage", "message"}:
                continue
            channel = message.get("channel") or message.get("pattern") or ""
            data = message.get("data")
            try:
                payload = json.loads(data) if isinstance(data, str) else data
            except Exception:
                continue
            topic = channel.split(":", 1)[-1] if isinstance(channel, str) else "events"
            await self._emit_local(topic, payload)

    async def subscribe(self, topic: str, listener: Listener) -> None:
        async with self._lock:
            self._listeners[topic].add(listener)

    async def unsubscribe(self, topic: str, listener: Listener) -> None:
        async with self._lock:
            self._listeners[topic].discard(listener)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        await self._emit_local(topic, payload)
        if self._redis is not None:
            try:
                await self._redis.publish(f"foxagent:{topic}", json.dumps(payload, default=str))
            except Exception as exc:
                logger.debug("Redis publish failed: %s", exc)

    async def _emit_local(self, topic: str, payload: dict[str, Any]) -> None:
        listeners = list(self._listeners.get(topic, set())) + list(self._listeners.get("*", set()))
        for listener in listeners:
            try:
                await listener(payload)
            except Exception:
                logger.exception("Listener failed for topic %s", topic)


bus = EventBus()
