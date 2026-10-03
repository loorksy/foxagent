"""Model ids the operator can choose. Claude stays the default; Z.ai is opt-in."""

from __future__ import annotations

CLAUDE_ALIASES = {
    "sonnet": "claude-sonnet-4-5",
    "sonnet-4": "claude-sonnet-4-5",
    "claude 3.7 sonnet": "claude-3-7-sonnet-latest",
    "claude-3.7-sonnet": "claude-3-7-sonnet-latest",
    "3.7": "claude-3-7-sonnet-latest",
    "claude 3.5 sonnet": "claude-3-5-sonnet-latest",
    "claude-3.5-sonnet": "claude-3-5-sonnet-latest",
    "haiku": "claude-3-5-haiku-latest",
    "claude 3.5 haiku": "claude-3-5-haiku-latest",
    "opus": "claude-opus-4-5",
}

# Official Z.ai chat model codes (docs.z.ai, overseas ZaiClient).
ZAI_MODELS: tuple[dict[str, str], ...] = (
    {"id": "glm-5.3", "label": "GLM-5.3", "badge": "Z.ai", "provider": "zai"},
    {"id": "glm-5.2", "label": "GLM-5.2", "badge": "Z.ai", "provider": "zai"},
    {"id": "glm-5.3-flash", "label": "GLM-5.3 Flash", "badge": "Z.ai", "provider": "zai"},
    {"id": "glm-5.3-flashx", "label": "GLM-5.3 FlashX", "badge": "Z.ai", "provider": "zai"},
)

ZAI_ALIASES = {
    "zai": "glm-5.3",
    "glm": "glm-5.3",
    "glm-5": "glm-5.3",
    "glm-5.3": "glm-5.3",
    "glm-5.2": "glm-5.2",
    "glm-5.3-flash": "glm-5.3-flash",
    "flash": "glm-5.3-flash",
    "glm-5.3-flashx": "glm-5.3-flashx",
    "flashx": "glm-5.3-flashx",
}

CLAUDE_MODELS: tuple[dict[str, str], ...] = (
    {"id": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "badge": "Default", "provider": "anthropic"},
    {"id": "claude-3-7-sonnet-latest", "label": "Claude 3.7 Sonnet", "badge": "Vision", "provider": "anthropic"},
    {"id": "claude-3-5-sonnet-latest", "label": "Claude 3.5 Sonnet", "badge": "Stable", "provider": "anthropic"},
    {"id": "claude-3-5-haiku-latest", "label": "Claude 3.5 Haiku", "badge": "Fast", "provider": "anthropic"},
    {"id": "claude-opus-4-5", "label": "Claude Opus 4.5", "badge": "Max", "provider": "anthropic"},
)

ZAI_MODEL_IDS = {row["id"] for row in ZAI_MODELS}
DEFAULT_ZAI_MODEL = "glm-5.3"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5"


def list_models() -> list[dict[str, str]]:
    return [dict(row) for row in (*CLAUDE_MODELS, *ZAI_MODELS)]


def resolve_model(name: str) -> str:
    key = (name or "").strip().lower()
    if key in ZAI_ALIASES:
        return ZAI_ALIASES[key]
    if key in CLAUDE_ALIASES:
        return CLAUDE_ALIASES[key]
    cleaned = (name or "").strip()
    return cleaned or DEFAULT_CLAUDE_MODEL


def is_zai_model(name: str) -> bool:
    return resolve_model(name) in ZAI_MODEL_IDS


def provider_for_model(name: str) -> str:
    return "zai" if is_zai_model(name) else "anthropic"
