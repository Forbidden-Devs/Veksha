"""
api/auth.py — registration endpoint.

  POST /api/auth/register {"username": "..."} → {"token": "...", "username": "..."}

The token is returned exactly once; the client stores it and presents it as
`Authorization: Bearer <token>` (HTTP) or `?token=` (WebSocket). There is no
login/recovery yet — a lost token means a new account (acceptable pre-launch;
Google OAuth is the planned replacement).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from storage import _safe_username

log = logging.getLogger(__name__)

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)


class RegisterResponse(BaseModel):
    username: str
    token: str


@router.post("/api/auth/register", response_model=RegisterResponse, status_code=201)
async def api_register(req: RegisterRequest) -> RegisterResponse:
    try:
        username = _safe_username(req.username)
    except ValueError:
        raise HTTPException(status_code=400, detail="Username must contain letters or digits.")

    token = db.create_user(username)
    if token is None:
        raise HTTPException(status_code=409, detail="Username is already taken.")

    log.info("[auth] registered user %r", username)
    return RegisterResponse(username=username, token=token)
