"""Actionable page-readiness analysis and vocabulary preparation."""

from __future__ import annotations

import asyncio
import re
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field
from wordfreq import tokenize

import textstats
from auth import CurrentUser
from cefr import level_to_cefr
from learning_core_v2.acquisition import SuggestVocabulary, VocabularyProposal
from learning_core_v2.dictionary import DictionaryLookupRequest
from learning_core_v2.reading_coach import AssessReading, ReadingToken
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import build_dictionary_enrichment
from storage import get_storage


router = APIRouter()
_MAX_TEXT_CHARACTERS = 12_000
_MAX_PREPARED_TERMS = 8


class ReadingCoachRequest(BaseModel):
    text: str = Field("", max_length=_MAX_TEXT_CHARACTERS)


class ReadingObstacleResponse(BaseModel):
    term: str
    occurrences: int
    cefr: str
    knowledge: str
    reason: str


class ReadingCoachResponse(BaseModel):
    known_pct: float
    projected_known_pct: float
    cefr: str
    user_level: str
    verdict: str
    confidence: str
    unique_terms: int
    obstacles: list[ReadingObstacleResponse]


class PrepareReadingRequest(BaseModel):
    text: str = Field("", max_length=_MAX_TEXT_CHARACTERS)
    terms: list[str] = Field(default_factory=list, max_length=_MAX_PREPARED_TERMS)
    source_url: str = Field("", max_length=2000)


class PrepareReadingResponse(BaseModel):
    added: int
    skipped: int


def _knowledge(storage, term: str, language: str) -> str:
    statuses = {
        item.status
        for item in storage.lexicon.all()
        if item.language == language
        and item.term.strip().casefold() == term.casefold()
    }
    for status in ("known", "learning", "suggested", "ignored"):
        if status in statuses:
            return status
    return "unseen"


@router.post("/api/reading-coach/analyze", response_model=ReadingCoachResponse)
async def analyze_reading(req: ReadingCoachRequest, username: CurrentUser) -> ReadingCoachResponse:
    storage = get_storage(username)
    language = storage.settings.target_lang or "en"
    learner = level_to_cefr(storage.settings.english_level)
    counts: dict[str, int] = {}
    for token in tokenize(req.text.casefold(), language):
        if any(character.isalpha() for character in token):
            counts[token] = counts.get(token, 0) + 1
    assessment = AssessReading().execute(
        [
            ReadingToken(
                term=term,
                occurrences=occurrences,
                cefr=textstats.band_for_word(term, language),
                knowledge=_knowledge(storage, term, language),
            )
            for term, occurrences in counts.items()
        ],
        learner_cefr=learner,
    )
    return ReadingCoachResponse(
        known_pct=round(assessment.known_ratio, 4),
        projected_known_pct=round(assessment.projected_known_ratio, 4),
        cefr=assessment.page_cefr,
        user_level=assessment.learner_cefr,
        verdict=assessment.verdict,
        confidence=assessment.confidence,
        unique_terms=assessment.unique_terms,
        obstacles=[
            ReadingObstacleResponse(
                term=item.term,
                occurrences=item.occurrences,
                cefr=item.cefr,
                knowledge=item.knowledge,
                reason=item.reason,
            )
            for item in assessment.obstacles
        ],
    )


@router.post("/api/reading-coach/prepare", response_model=PrepareReadingResponse)
async def prepare_reading(req: PrepareReadingRequest, username: CurrentUser) -> PrepareReadingResponse:
    storage = get_storage(username)
    language = storage.settings.target_lang or "en"
    native_language = storage.settings.native_lang or "en"
    text = " ".join(req.text.split())
    available = {
        token.casefold()
        for token in tokenize(text.casefold(), language)
        if any(character.isalpha() for character in token)
    }
    requested = list(dict.fromkeys(" ".join(term.split()).casefold() for term in req.terms))
    eligible = [
        term
        for term in requested
        if term and term in available and _knowledge(storage, term, language) == "unseen"
    ][:_MAX_PREPARED_TERMS]
    service = build_dictionary_enrichment()
    semaphore = asyncio.Semaphore(3)

    async def enrich(term: str):
        try:
            async with semaphore:
                return await service.execute(
                    DictionaryLookupRequest(
                        term=term,
                        learning_language=language,
                        native_language=native_language,
                        proficiency=storage.settings.english_level or "intermediate",
                        context=_context_for(term, text),
                    )
                )
        except (LanguageProviderError, ValueError):
            return None

    details = await asyncio.gather(*(enrich(term) for term in eligible))
    suggest = SuggestVocabulary()
    added = 0
    for term, detail in zip(eligible, details, strict=True):
        if detail is None:
            continue
        before = len(storage.lexicon)
        storage.lexicon.replace_all(
            suggest.execute(
                storage.lexicon.all(),
                VocabularyProposal(
                    term=detail.headword or term,
                    language=language,
                    translation=detail.translation,
                    transcription=detail.transcription,
                    context=_context_for(term, text),
                    source_url=req.source_url,
                ),
                observed_at=time.time(),
            )
        )
        if len(storage.lexicon) > before:
            added += 1
    if added:
        storage.save()
    return PrepareReadingResponse(added=added, skipped=len(requested) - added)


def _context_for(term: str, text: str) -> str:
    fragments = re.split(r"(?<=[.!?])\s+|\n+", text)
    return next(
        (fragment[:500] for fragment in fragments if term.casefold() in fragment.casefold()),
        text[:500],
    )
