"""
api/message.py — /api/message endpoint (assistant chat pipeline).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

import pipeline
from auth import CurrentUser
from session_state import SessionState
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    messages: list[str]


@router.post("/api/message", response_model=MessageResponse)
async def api_message(req: MessageRequest, username: CurrentUser) -> MessageResponse:
    storage = get_storage(username)
    session = SessionState.load(username)

    session.add_history("user", req.text)
    context = session.history_as_text(last_n=3)

    result = await pipeline.process_message(storage, req.text, context)
    for m in result.messages:
        session.add_history("assistant", m)
    session.save()

    return MessageResponse(messages=result.messages)
