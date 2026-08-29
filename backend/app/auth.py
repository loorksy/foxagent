from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse

from app.config import get_settings

COOKIE_NAME = "foxagent_token"
ALGORITHM = "HS256"
PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/logout"}


def _jwt_secret() -> str:
    settings = get_settings()
    secret = (settings.jwt_secret or settings.settings_secret or "").strip()
    if not secret:
        secret = "foxagent-dev-jwt-secret"
    return secret


def password_configured() -> bool:
    settings = get_settings()
    return bool(settings.admin_password_hash.strip() or settings.app_password.strip())


def verify_password(plain: str) -> bool:
    settings = get_settings()
    hashed = settings.admin_password_hash.strip()
    if hashed:
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False
    expected = settings.app_password
    if not expected:
        return False
    return hmac.compare_digest(plain.encode("utf-8"), expected.encode("utf-8"))


def issue_token(*, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = settings.jwt_expire_minutes if expires_minutes is None else expires_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "operator",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def extract_request_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip() or None
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    return request.query_params.get("token")


def extract_ws_token(ws: WebSocket) -> str | None:
    header = ws.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip() or None
    cookie_header = ws.headers.get("cookie") or ""
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME and value:
            return value
    return ws.query_params.get("token")


def require_token(token: str | None) -> dict[str, Any]:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(token)


def set_auth_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=get_settings().jwt_expire_minutes * 60,
    )


def clear_auth_cookie(response: JSONResponse) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
