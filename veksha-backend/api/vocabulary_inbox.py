"""HTTP boundary for vocabulary suggestions awaiting a learner decision."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import CurrentUser
from learning_core_v2.acquisition import DecideVocabulary, LexicalItem
from storage import get_storage


router = APIRouter()


class InboxItemResponse(BaseModel):
    item_id: str
    term: str
    language: str
    translation: str
    transcription: str
    encounter_count: int
    latest_context: str
    latest_source_url: str
    last_seen_at: float


class InboxResponse(BaseModel):
    items: list[InboxItemResponse]


class InboxDecisionRequest(BaseModel):
    decision: Literal["learn", "known", "ignore"]


class InboxDecisionResponse(BaseModel):
    item_id: str
    status: Literal["learning", "known", "ignored"]


def _response(item: LexicalItem) -> InboxItemResponse:
    latest = item.encounters[-1] if item.encounters else None
    return InboxItemResponse(
        item_id=item.item_id,
        term=item.term,
        language=item.language,
        translation=item.translation,
        transcription=item.transcription,
        encounter_count=len(item.encounters),
        latest_context=latest.context if latest else "",
        latest_source_url=latest.source_url if latest else "",
        last_seen_at=latest.observed_at if latest else 0.0,
    )


@router.get("/api/vocabulary-inbox", response_model=InboxResponse)
async def vocabulary_inbox(username: CurrentUser) -> InboxResponse:
    storage = get_storage(username)
    language = storage.settings.target_lang.lower().replace("_", "-")
    pending = list(storage.lexicon.pending(language))
    pending.sort(
        key=lambda item: item.encounters[-1].observed_at if item.encounters else 0.0,
        reverse=True,
    )
    return InboxResponse(items=[_response(item) for item in pending])


@router.post(
    "/api/vocabulary-inbox/{item_id}/decision",
    response_model=InboxDecisionResponse,
)
async def decide_vocabulary_inbox_item(
    item_id: str,
    req: InboxDecisionRequest,
    username: CurrentUser,
) -> InboxDecisionResponse:
    if not item_id or len(item_id) > 100:
        raise HTTPException(status_code=422, detail="Invalid vocabulary item id.")
    storage = get_storage(username)
    item = storage.lexicon.find(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Vocabulary suggestion not found.")
    try:
        decided = DecideVocabulary().execute(item, req.decision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if req.decision in {"learn", "known"} and decided.schedule.added_at <= 0:
        decided = replace(
            decided,
            schedule=replace(decided.schedule, added_at=time.time()),
        )

    storage.lexicon.replace(decided)
    storage.save()
    return InboxDecisionResponse(item_id=item.item_id, status=decided.status)
