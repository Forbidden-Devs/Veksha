"""Actionable page-readiness analysis and vocabulary preparation."""

from __future__ import annotations

import asyncio
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from wordfreq import tokenize

import textstats
from auth import CurrentUser
from cefr import level_to_cefr
from entitlements import require_feature
from learning_core_v2.acquisition import SuggestVocabulary, VocabularyProposal
from learning_core_v2.dictionary import DictionaryLookupRequest
from learning_core_v2.reading_coach import AssessReading, ReadingToken
from learning_core_v2.reading_coach import ReadingAnswerRequest, ReadingQuestionRequest
from learning_core_v2.explanation import ExplanationRequest
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import (
    build_deferred_translate_text,
    build_dictionary_enrichment,
    build_explain_text,
    build_reading_comprehension_services,
)
from api.translate_v2 import TranslateRequest, _execute_translation
from storage import get_storage


router = APIRouter()
_MAX_TEXT_CHARACTERS = 12_000
_MAX_PREPARED_TERMS = 8
_QUESTION_TTL_SECONDS = 15 * 60
_questions: dict[str, tuple[str, str, str, float]] = {}


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
    lexical_cefr: str
    structure_cefr: str
    average_sentence_words: float
    long_sentence_ratio: float
    obstacles: list[ReadingObstacleResponse]


class PrepareReadingRequest(BaseModel):
    text: str = Field("", max_length=_MAX_TEXT_CHARACTERS)
    terms: list[str] = Field(default_factory=list, max_length=_MAX_PREPARED_TERMS)
    source_url: str = Field("", max_length=2000)


class PrepareReadingResponse(BaseModel):
    added: int
    skipped: int


class ParagraphHelpRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=3000)


class ParagraphHelpResponse(BaseModel):
    original: str
    translation: str
    explanation: str


class ComprehensionQuestionRequest(BaseModel):
    text: str = Field(..., min_length=40, max_length=3000)


class ComprehensionQuestionResponse(BaseModel):
    question_id: str
    question: str


class ComprehensionAnswerRequest(BaseModel):
    question_id: str = Field(..., min_length=16, max_length=128)
    answer: str = Field(..., max_length=2000)


class ComprehensionAnswerResponse(BaseModel):
    outcome: str
    feedback: str


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
    tokens = [
        ReadingToken(
            term=term,
            occurrences=occurrences,
            cefr=textstats.band_for_word(term, language),
            knowledge=_knowledge(storage, term, language),
        )
        for term, occurrences in counts.items()
    ]
    structure = textstats.estimate_structure(req.text, language)
    lexical_assessment = AssessReading().execute(tokens, learner_cefr=learner)
    assessment = AssessReading().execute(
        tokens,
        learner_cefr=learner,
        structure_cefr=structure.cefr,
    )
    return ReadingCoachResponse(
        known_pct=round(assessment.known_ratio, 4),
        projected_known_pct=round(assessment.projected_known_ratio, 4),
        cefr=assessment.page_cefr,
        user_level=assessment.learner_cefr,
        verdict=assessment.verdict,
        confidence=assessment.confidence,
        unique_terms=assessment.unique_terms,
        lexical_cefr=lexical_assessment.page_cefr,
        structure_cefr=structure.cefr,
        average_sentence_words=structure.average_sentence_words,
        long_sentence_ratio=structure.long_sentence_ratio,
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


@router.post(
    "/api/reading-coach/paragraph-help",
    response_model=ParagraphHelpResponse,
    dependencies=[Depends(require_feature("immersion"))],
)
async def help_with_paragraph(
    req: ParagraphHelpRequest, username: CurrentUser
) -> ParagraphHelpResponse:
    storage = get_storage(username)
    original = " ".join(req.text.split())
    translation_service, _, _ = build_deferred_translate_text(storage)
    try:
        translated = await _execute_translation(
            TranslateRequest(
                text=original,
                source_lang=storage.settings.target_lang or "auto",
                target_lang=storage.settings.native_lang or "en",
            ),
            storage,
            translation_service,
        )
        explained = await build_explain_text().execute(
            ExplanationRequest(
                text=original,
                translation=translated.translation,
                proficiency=storage.settings.english_level or "intermediate",
                native_language=storage.settings.native_lang or "en",
                learning_language=storage.settings.target_lang or "en",
            )
        )
    except (LanguageProviderError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Paragraph help unavailable.") from exc
    return ParagraphHelpResponse(
        original=original,
        translation=translated.translation,
        explanation=explained.explanation,
    )


@router.post(
    "/api/reading-coach/comprehension/question",
    response_model=ComprehensionQuestionResponse,
    dependencies=[Depends(require_feature("immersion"))],
)
async def create_comprehension_question(
    req: ComprehensionQuestionRequest, username: CurrentUser
) -> ComprehensionQuestionResponse:
    storage = get_storage(username)
    builder, _ = build_reading_comprehension_services()
    passage = " ".join(req.text.split())
    try:
        question = await builder.execute(
            ReadingQuestionRequest(
                passage=passage,
                learner_cefr=level_to_cefr(storage.settings.english_level),
                learning_language=storage.settings.target_lang or "en",
                native_language=storage.settings.native_lang or "en",
            )
        )
    except (LanguageProviderError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Comprehension question unavailable.") from exc
    now = time.monotonic()
    for key, value in list(_questions.items()):
        if value[3] <= now:
            _questions.pop(key, None)
    if len(_questions) >= 500:
        oldest = min(_questions, key=lambda key: _questions[key][3])
        _questions.pop(oldest, None)
    question_id = secrets.token_urlsafe(24)
    _questions[question_id] = (username, passage, question, now + _QUESTION_TTL_SECONDS)
    return ComprehensionQuestionResponse(question_id=question_id, question=question)


@router.post(
    "/api/reading-coach/comprehension/check",
    response_model=ComprehensionAnswerResponse,
    dependencies=[Depends(require_feature("immersion"))],
)
async def check_comprehension_answer(
    req: ComprehensionAnswerRequest, username: CurrentUser
) -> ComprehensionAnswerResponse:
    stored = _questions.get(req.question_id)
    if not stored or stored[0] != username or stored[3] <= time.monotonic():
        raise HTTPException(status_code=404, detail="Reading question expired.")
    _questions.pop(req.question_id, None)
    storage = get_storage(username)
    _, checker = build_reading_comprehension_services()
    try:
        result = await checker.execute(
            ReadingAnswerRequest(
                passage=stored[1],
                question=stored[2],
                answer=req.answer,
                learner_cefr=level_to_cefr(storage.settings.english_level),
                learning_language=storage.settings.target_lang or "en",
                native_language=storage.settings.native_lang or "en",
            )
        )
    except (LanguageProviderError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Answer check unavailable.") from exc
    return ComprehensionAnswerResponse(outcome=result.outcome, feedback=result.feedback)


@router.post(
    "/api/reading-coach/prepare",
    response_model=PrepareReadingResponse,
    dependencies=[Depends(require_feature("immersion"))],
)
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
