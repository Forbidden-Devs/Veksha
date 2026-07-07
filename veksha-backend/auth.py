"""auth.py — bearer-token authentication dependencies.

HTTP endpoints:   Authorization: Bearer <token>  → CurrentUser (username)
WebSocket routes: ?token=<token> query parameter → ws_current_user()
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, WebSocket

import db

log = logging.getLogger(__name__)


async def current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization[len("Bearer "):].strip()
    username = db.token_owner(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return username


CurrentUser = Annotated[str, Depends(current_user)]


async def ws_current_user(websocket: WebSocket) -> Optional[str]:
    """Resolve the user for a WebSocket connection; returns None if unauthorized
    (caller should close with 4401)."""
    token = websocket.query_params.get("token", "")
    return db.token_owner(token)
