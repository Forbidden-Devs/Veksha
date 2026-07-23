"""
api/vocab_frequency.py — "real browsing" personal frequency list.

  POST /api/vocab_frequency/track — count the words in a page-text sample
  the user actually read (tagged by the site's domain).
  GET  /api/vocab_frequency/top   — the resulting personal frequency list,
  cross-referenced against the KB so each word is flagged known/unknown.

Pure local computation (wordfreq tokenizing + PostgreSQL counters) — no LLM
calls, unlike CI Meter/Grammar Lens.
"""
from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel, Field
from wordfreq import tokenize

import db
import textstats
from auth import CurrentUser
from storage import get_storage

router = APIRouter()

_MAX_TEXT_CHARS = 8000
_DEFAULT_LIMIT = 100


class TrackRequest(BaseModel):
    text: str = ""
    domain: str = ""


class TrackResponse(BaseModel):
    tracked: int


class VocabFrequencyEntry(BaseModel):
    word: str
    count: int
    domains: dict[str, int] = Field(default_factory=dict)
    known: bool = False
    in_dictionary: bool = False


class VocabFrequencyResponse(BaseModel):
    words: list[VocabFrequencyEntry]


@router.post("/api/vocab_frequency/track", response_model=TrackResponse)
async def api_vocab_frequency_track(req: TrackRequest, username: CurrentUser) -> TrackResponse:
    storage = get_storage(username)
    target = storage.settings.target_lang or "en"
    domain = (req.domain or "").strip().lower()[:200] or "unknown"

    text = (req.text or "").strip()[:_MAX_TEXT_CHARS]
    tokens = [t for t in tokenize(text.lower(), target) if any(c.isalpha() for c in t)]
    # Skip ultra-common function words (A1 band) — they'd dominate every
    # page's counts without being useful "vocabulary you should learn".
    counts: dict[str, int] = {}
    for tok in tokens:
        if textstats.band_for_word(tok, target) == "A1":
            continue
        counts[tok] = counts.get(tok, 0) + 1

    db.word_freq_bump_many(username, target, counts, domain, time.time())
    return TrackResponse(tracked=len(counts))


@router.get("/api/vocab_frequency/top", response_model=VocabFrequencyResponse)
async def api_vocab_frequency_top(username: CurrentUser, limit: int = _DEFAULT_LIMIT) -> VocabFrequencyResponse:
    storage = get_storage(username)
    target = storage.settings.target_lang or "en"

    dictionary_words = {
        w.name.strip().lower(): bool(w.known)
        for w in storage.words
        if w.language == target
    }

    rows = db.word_freq_top(username, target, limit)
    return VocabFrequencyResponse(words=[
        VocabFrequencyEntry(
            word=row["word"],
            count=row["count"],
            domains=row["domains"],
            known=dictionary_words.get(row["word"], False),
            in_dictionary=row["word"] in dictionary_words,
        )
        for row in rows
    ])
