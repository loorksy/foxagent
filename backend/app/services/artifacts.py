from __future__ import annotations

from typing import Any, Callable, Awaitable
from uuid import uuid4

from app.schemas import utcnow
from app.services.session_store import append_session_event

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


def new_artifact_id() -> str:
    return f"art_{uuid4().hex[:12]}"


async def stream_artifact(
    emit: Emit,
    *,
    session_id: str | None,
    title: str,
    artifact_type: str,
    body: str,
    agent: str,
    run_id: str,
) -> dict[str, Any]:
    artifact = {
        "id": new_artifact_id(),
        "title": title,
        "type": artifact_type,
        "agent": agent,
        "body": "",
        "createdAt": utcnow().isoformat(),
        "runId": run_id,
    }
    await emit("agent_artifact_start", {k: artifact[k] for k in ("id", "title", "type", "agent", "runId")})
    chunk = 280
    acc = []
    for i in range(0, len(body), chunk):
        part = body[i : i + chunk]
        acc.append(part)
        await emit("agent_artifact_delta", {"id": artifact["id"], "text": part, "runId": run_id})
    artifact["body"] = "".join(acc)
    await emit("agent_artifact_end", artifact)
    if session_id:
        await append_session_event(session_id, "artifact", artifact)
    return artifact
