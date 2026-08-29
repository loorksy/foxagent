from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import (
    clear_auth_cookie,
    extract_request_token,
    issue_token,
    password_configured,
    require_token,
    set_auth_cookie,
    verify_password,
)

router = APIRouter()


class LoginBody(BaseModel):
    password: str = ""


@router.post("/auth/login")
async def login(body: LoginBody) -> JSONResponse:
    if not password_configured():
        raise HTTPException(status_code=503, detail="Operator password is not configured")
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = issue_token()
    response = JSONResponse({"ok": True, "operator": True})
    set_auth_cookie(response, token)
    return response


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    clear_auth_cookie(response)
    return response


@router.get("/auth/me")
async def me(request: Request) -> dict:
    payload = require_token(extract_request_token(request))
    return {"ok": True, "operator": payload.get("sub") == "operator"}
