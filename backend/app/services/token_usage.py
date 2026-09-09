"""Meter Anthropic token usage from official response.usage fields.

Numbers come from the API, not local estimators. USD is a UI estimate only.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

# Approximate public list prices (USD per million tokens). UI only — not billing.
_RATES: dict[str, tuple[float, float]] = {
    "claude-opus-4-5": (15.0, 75.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-3-7-sonnet": (3.0, 15.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "claude-haiku": (0.8, 4.0),
}
_CACHE_READ = 0.1
_CACHE_WRITE = 1.25


def _rates_for(model: str) -> tuple[float, float]:
    key = (model or "").lower()
    for prefix, pair in _RATES.items():
        if prefix in key:
            return pair
    return (3.0, 15.0)


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _attr(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        for name in names:
            if name in obj and obj[name] is not None:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return None


@dataclass
class TokenSlice:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def empty(self) -> bool:
        return self.total_tokens == 0

    def add(self, other: "TokenSlice") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens

    def estimate_usd(self, model: str) -> float:
        inp, out = _rates_for(model)
        billed_in = (
            self.input_tokens
            + self.cache_creation_input_tokens * _CACHE_WRITE
            + self.cache_read_input_tokens * _CACHE_READ
        )
        return (billed_in * inp + self.output_tokens * out) / 1_000_000

    def public(self, *, model: str = "", agent: str = "", path: str = "") -> dict[str, Any]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cacheCreationTokens": self.cache_creation_input_tokens,
            "cacheReadTokens": self.cache_read_input_tokens,
            "totalTokens": self.total_tokens,
            "estimatedUsd": round(self.estimate_usd(model), 4),
            "model": model,
            "agent": agent,
            "path": path,
        }


def parse_usage(raw: Any) -> TokenSlice:
    """Accept Message.usage, stream message_delta.usage, or SDK ResultMessage."""
    if raw is None:
        return TokenSlice()
    usage = _attr(raw, "usage") or raw
    if _attr(usage, "type") in {"message_delta", "message_start"}:
        usage = _attr(raw, "usage") or _attr(_attr(raw, "message"), "usage") or usage
    creation = _attr(usage, "cache_creation_input_tokens", "cacheCreationInputTokens")
    if creation is None:
        nested = _attr(usage, "cache_creation", "cacheCreation")
        creation = 0
        if nested is not None:
            creation = _as_int(_attr(nested, "ephemeral_5m_input_tokens")) + _as_int(
                _attr(nested, "ephemeral_1h_input_tokens")
            )
    return TokenSlice(
        input_tokens=_as_int(_attr(usage, "input_tokens", "inputTokens", "uncached_input_tokens")),
        output_tokens=_as_int(_attr(usage, "output_tokens", "outputTokens")),
        cache_creation_input_tokens=_as_int(creation),
        cache_read_input_tokens=_as_int(_attr(usage, "cache_read_input_tokens", "cacheReadInputTokens")),
    )


@dataclass
class UsageTracker:
    run_id: str
    model: str = ""
    totals: TokenSlice = field(default_factory=TokenSlice)
    calls: int = 0

    def add(self, slice: TokenSlice, *, model: str = "") -> None:
        if slice.empty():
            return
        self.totals.add(slice)
        self.calls += 1
        if model:
            self.model = model

    def public(self) -> dict[str, Any]:
        body = self.totals.public(model=self.model)
        body["runId"] = self.run_id
        body["calls"] = self.calls
        return body


_current: ContextVar[UsageTracker | None] = ContextVar("fox_usage_tracker", default=None)


def bind_usage_tracker(tracker: UsageTracker) -> Token:
    return _current.set(tracker)


def reset_usage_tracker(token: Token) -> None:
    _current.reset(token)


def current_tracker() -> UsageTracker | None:
    return _current.get()


async def record_model_usage(
    raw: Any,
    *,
    emit: Any,
    run_id: str,
    model: str,
    agent: str = "",
    path: str = "",
) -> TokenSlice:
    slice = parse_usage(raw)
    if slice.empty():
        return slice
    tracker = current_tracker()
    if tracker is not None:
        tracker.add(slice, model=model)
        payload = tracker.public()
    else:
        payload = slice.public(model=model, agent=agent, path=path)
        payload["runId"] = run_id
        payload["calls"] = 1
    payload["agent"] = agent
    payload["path"] = path
    if emit:
        await emit("usage", payload)
    return slice
