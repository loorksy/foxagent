from __future__ import annotations

import base64
import re
from pathlib import Path

from app.config import DATA_DIR
from app.schemas import new_id

SHOT_DIR = DATA_DIR / "chart_shots"
_SHOT_RE = re.compile(r"^img_[a-f0-9]{12}$")


def _dir() -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SHOT_DIR


def save_chart_shot(b64: str) -> dict[str, str] | None:
    raw = (b64 or "").strip()
    if not raw:
        return None
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:
        return None
    if len(data) < 32 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    shot_id = new_id("img")
    path = _dir() / f"{shot_id}.png"
    path.write_bytes(data)
    return {"id": shot_id, "url": f"/api/agent/images/{shot_id}"}


def shot_path(shot_id: str) -> Path | None:
    if not _SHOT_RE.match(shot_id or ""):
        return None
    path = _dir() / f"{shot_id}.png"
    return path if path.is_file() else None
