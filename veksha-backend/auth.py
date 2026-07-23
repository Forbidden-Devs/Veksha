"""auth.py — bearer-token authentication dependencies.

HTTP endpoints:   Authorization: Bearer <token>  → CurrentUser (username)
WebSocket routes: first message {"type": "auth", "token": "..."}
                  → ws_current_user() (accepts + authenticates the socket)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, WebSocket

import db
from usage_context import set_usage_user

log = logging.getLogger(__name__)

# How long a fresh WebSocket connection may take to send its auth message.
WS_AUTH_TIMEOUT_SECONDS = 10.0


async def current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization[len("Bearer "):].strip()
    username = db.token_owner(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token.")
    set_usage_user(username)
    return username


CurrentUser = Annotated[str, Depends(current_user)]


async def ws_current_user(websocket: WebSocket) -> Optional[str]:
    """Accept the connection and authenticate it via the first message:

        {"type": "auth", "token": "<bearer token>"}

    The token deliberately does not travel in the URL — query strings end up
    in access logs and proxy logs. Returns the username, or None after
    closing the socket (code 4401) on a missing/invalid/late auth message.
    """
    await websocket.accept()
    token = ""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), WS_AUTH_TIMEOUT_SECONDS)
        msg = json.loads(raw)
        if isinstance(msg, dict) and msg.get("type") == "auth":
            token = str(msg.get("token") or "")
    except Exception:
        token = ""

    username = db.token_owner(token) if token else None
    if username is None:
        log.info("[auth] websocket auth failed (%s)", "no token" if not token else "bad token")
        try:
            await websocket.close(code=4401)
        except Exception:
            pass
        return None
    set_usage_user(username)
    return username
