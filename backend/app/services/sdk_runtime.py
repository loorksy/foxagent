"""Claude Agent SDK primary path + countable fallback.

Official pattern (anthropics/claude-agent-sdk-python README):
  @tool + create_sdk_mcp_server + ClaudeSDKClient(options) + client.query
  + receive_response.

Fallback is only for transient transport/rate-limit failures. Configuration
bugs (missing CLI, import errors, unusable options) raise instead of being
silently routed around.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

SDK_TOOLS = [
    "mcp__oanda__get_candles",
    "mcp__oanda__get_live_price",
    "mcp__oanda__capture_chart_screenshot",
    "mcp__oanda__structure_scan",
    "mcp__oanda__calculate_ict_levels",
    "mcp__oanda__query_technical_memory",
    "mcp__oanda__get_economic_calendar",
    "mcp__oanda__get_market_sentiment",
    "mcp__oanda__fetch_financial_news",
    "mcp__oanda__query_macro_memory",
    "mcp__oanda__validate_risk_rules",
    "mcp__oanda__send_recommendation",
    "mcp__oanda__record_post_trade_reflection",
    "mcp__oanda__draw_on_chart",
]


@dataclass
class SdkPathStats:
    success: int = 0
    fallback: int = 0
    config_error: int = 0
    last_fallback_reason: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            total = self.success + self.fallback
            rate = (self.success / total) if total else None
            return {
                "sdkPathSuccessCount": self.success,
                "sdkPathFallbackCount": self.fallback,
                "sdkPathConfigErrorCount": self.config_error,
                "sdkPathSuccessRate": rate,
                "sdkPathLastFallbackReason": self.last_fallback_reason,
            }

    def record_success(self) -> None:
        with self.lock:
            self.success += 1

    def record_fallback(self, reason: str) -> None:
        with self.lock:
            self.fallback += 1
            self.last_fallback_reason = reason

    def record_config_error(self, reason: str) -> None:
        with self.lock:
            self.config_error += 1
            self.last_fallback_reason = reason

    def reset(self) -> None:
        with self.lock:
            self.success = 0
            self.fallback = 0
            self.config_error = 0
            self.last_fallback_reason = ""


stats = SdkPathStats()

_TRANSIENT_NAMES = {
    "CLIConnectionError",
    "ProcessError",
    "ResultError",
    "RateLimitEvent",
    "TimeoutError",
    "APIStatusError",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
}

_CONFIG_NAMES = {
    "CLINotFoundError",
    "ImportError",
    "ModuleNotFoundError",
    "TypeError",
    "CLIJSONDecodeError",
}


def classify_sdk_failure(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if name in _CONFIG_NAMES:
        return "config"
    if name in _TRANSIENT_NAMES:
        return "transient"
    if "rate limit" in text or "429" in text or "timeout" in text or "temporar" in text:
        return "transient"
    if ("cli" in text and "not found" in text) or "argument list too long" in text:
        return "config"
    return "transient"


def build_sdk_options(*, model: str, system: str, api_key: str, server: Any, max_turns: int = 8) -> Any:
    from claude_agent_sdk import ClaudeAgentOptions

    # Official isolation (claude-agent-sdk 0.2.x ClaudeAgentOptions):
    # tools=[] disables built-in Claude Code FS tools; allowed_tools auto-approves
    # our in-process MCP tools; dontAsk denies anything not pre-approved; 
    # setting_sources=[] + strict_mcp_config=True ignore leaked project/user MCP.
    kwargs: dict[str, Any] = {
        "model": model,
        "system_prompt": system,
        "mcp_servers": {"oanda": server},
        "allowed_tools": list(SDK_TOOLS),
        "permission_mode": "dontAsk",
        "env": {"ANTHROPIC_API_KEY": api_key},
        "max_turns": max_turns,
        "tools": [],
        "setting_sources": [],
        "strict_mcp_config": True,
    }
    try:
        return ClaudeAgentOptions(**kwargs)
    except TypeError:
        kwargs.pop("tools", None)
        kwargs.pop("setting_sources", None)
        kwargs.pop("strict_mcp_config", None)
        try:
            return ClaudeAgentOptions(**kwargs)
        except TypeError:
            kwargs["permission_mode"] = "acceptEdits"
            return ClaudeAgentOptions(**kwargs)


def vision_user_content(text: str, image_b64: str | None) -> Any:
    """Official Claude vision block: image first, then text (docs.claude.com/vision)."""
    if not image_b64:
        return text
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
        },
        {"type": "text", "text": text},
    ]


def sdk_query_arg(text: str, image_b64: str | None) -> Any:
    """String prompt, or official streaming user message with image content blocks.

    ClaudeSDKClient.query accepts str | AsyncIterable[dict]. Image turns must use
    the streaming form so the CLI receives Anthropic image source blocks.
    """
    if not image_b64:
        return text

    async def _stream():
        yield {
            "type": "user",
            "message": {"role": "user", "content": vision_user_content(text, image_b64)},
            "parent_tool_use_id": None,
        }

    return _stream()
