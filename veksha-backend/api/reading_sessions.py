"""Explicit Reading Sessions and their vocabulary observations."""
from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from wordfreq import tokenize

import db
import textstats
from auth import CurrentUser
from storage import get_storage

router = APIRouter()

_MAX_TEXT_CHARS = 8000
_DEFAULT_LIMIT = 100


class StartRequest(BaseModel):
    source_url: str = Field("", max_length=2000)


class SessionResponse(BaseModel):
    session_id: str
    started_at: float


class ObserveRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=80)
    text: str = ""
    domain: str = ""


class ObserveResponse(BaseModel):
    observed: int


class EndRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=80)


class ReadingVocabularyEntry(BaseModel):
    word: str
    count: int
    domains: dict[str, int] = Field(default_factory=dict)
    known: bool = False
    in_dictionary: bool = False


class ReadingVocabularyResponse(BaseModel):
    words: list[ReadingVocabularyEntry]


@router.post("/api/reading-sessions", response_model=SessionResponse)
async def start_reading_session(req: StartRequest, username: CurrentUser) -> SessionResponse:
    storage = get_storage(username)
    started_at = time.time()
    session_id = uuid4().hex
    db.reading_session_start(
        session_id,
        username,
        storage.settings.target_lang or "en",
        req.source_url.strip(),
        started_at,
    )
    return SessionResponse(session_id=session_id, started_at=started_at)


@router.post("/api/reading-sessions/observe", response_model=ObserveResponse)
async def observe_reading_session(
    req: ObserveRequest,
    username: CurrentUser,
) -> ObserveResponse:
    target = get_storage(username).settings.target_lang or "en"
    text = req.text.strip()[:_MAX_TEXT_CHARS]
    counts: dict[str, int] = {}
    for token in tokenize(text.lower(), target):
        if not any(char.isalpha() for char in token):
            continue
        if textstats.band_for_word(token, target) == "A1":
            continue
        counts[token] = counts.get(token, 0) + 1
    accepted = db.reading_session_observe(
        req.session_id,
        username,
        counts,
        req.domain.strip().lower()[:200] or "unknown",
        time.time(),
    )
    if not accepted:
        raise HTTPException(status_code=409, detail="Reading session is not active")
    return ObserveResponse(observed=len(counts))


@router.post("/api/reading-sessions/end")
async def end_reading_session(req: EndRequest, username: CurrentUser) -> dict[str, bool]:
    if not db.reading_session_end(req.session_id, username, time.time()):
        raise HTTPException(status_code=404, detail="Active reading session not found")
    return {"ok": True}


@router.get("/api/reading-sessions/vocabulary", response_model=ReadingVocabularyResponse)
async def reading_session_vocabulary(
    username: CurrentUser,
    limit: int = _DEFAULT_LIMIT,
) -> ReadingVocabularyResponse:
    storage = get_storage(username)
    target = storage.settings.target_lang or "en"
    dictionary_words: dict[str, bool] = {}
    for item in storage.lexicon.all():
        if item.language == target and item.status in {"learning", "known"}:
            term = item.term.strip().lower()
            dictionary_words[term] = dictionary_words.get(term, False) or item.status == "known"
    rows = db.reading_session_vocabulary(username, target, limit)
    return ReadingVocabularyResponse(words=[
        ReadingVocabularyEntry(
            word=row["word"],
            count=row["count"],
            domains=row["domains"],
            known=dictionary_words.get(row["word"], False),
            in_dictionary=row["word"] in dictionary_words,
        )
        for row in rows
    ])
