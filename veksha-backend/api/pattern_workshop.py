"""Pattern Workshop: analyze a chosen sentence, practise one pattern, then save it."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from entitlements import require_feature
from learning_core_v2.grammar_analysis import GrammarAnalysisRequest
from learning_core_v2.grammar_memory import GrammarMemoryItem, GrammarObservation, RememberGrammar
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import build_grammar_analyzer
from storage import get_storage

router = APIRouter()
_MIN_TEXT_CHARS = 8
_MAX_TEXT_CHARS = 1000
_DRAFT_TTL_SECONDS = 30 * 60


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=_MIN_TEXT_CHARS, max_length=_MAX_TEXT_CHARS)
    source_url: str = Field("", max_length=2000)


class SegmentResponse(BaseModel):
    text: str
    role: str
    explanation: str = ""


class PatternChoiceResponse(BaseModel):
    index: int
    text: str
    category: str
    label: str
    explanation: str = ""
    contrast_example: str
    challenge_prompt: str


class AnalyzeResponse(BaseModel):
    draft_id: str
    text: str
    segments: list[SegmentResponse]
    patterns: list[PatternChoiceResponse]


class CompleteRequest(BaseModel):
    draft_id: str = Field(..., min_length=1, max_length=80)
    pattern_index: int = Field(..., ge=0, le=2)
    answer: str = Field(..., min_length=1, max_length=200)


class ErrorDraftRequest(BaseModel):
    source: Literal["training", "ai_correction", "text_check"]
    original: str = Field(..., min_length=1, max_length=_MAX_TEXT_CHARS)
    correction: str = Field(..., min_length=1, max_length=_MAX_TEXT_CHARS)
    category: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=160)
    explanation: str = Field("", max_length=1000)


class SkillResponse(BaseModel):
    item_id: str
    category: str
    label: str
    explanation: str
    status: str
    practice_count: int


@dataclass(frozen=True)
class _DraftPattern:
    text: str
    category: str
    label: str
    explanation: str


@dataclass(frozen=True)
class _Draft:
    username: str
    language: str
    text: str
    source_url: str
    patterns: tuple[_DraftPattern, ...]
    expires_at: float


_drafts: dict[str, _Draft] = {}


def _clean_expired_drafts(now: float) -> None:
    for draft_id in [key for key, value in _drafts.items() if value.expires_at <= now]:
        _drafts.pop(draft_id, None)


@router.post(
    "/api/pattern-workshop/analyze",
    response_model=AnalyzeResponse,
    dependencies=[Depends(require_feature("pattern_workshop"))],
)
async def analyze_pattern_workshop(req: AnalyzeRequest, username: CurrentUser) -> AnalyzeResponse:
    storage = get_storage(username)
    text = " ".join(req.text.split())
    try:
        analysis = await build_grammar_analyzer().execute(
            GrammarAnalysisRequest(
                text,
                storage.settings.native_lang or "en",
                storage.settings.english_level or "unknown",
            )
        )
    except (LanguageProviderError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Pattern analysis unavailable") from exc
    patterns = tuple(
        _DraftPattern(item.text, item.category, item.label, item.explanation)
        for item in analysis.annotations[:3]
    )
    now = time.time()
    _clean_expired_drafts(now)
    draft_id = uuid4().hex
    _drafts[draft_id] = _Draft(
        username=username,
        language=storage.settings.target_lang or "en",
        text=text,
        source_url=req.source_url,
        patterns=patterns,
        expires_at=now + _DRAFT_TTL_SECONDS,
    )
    return AnalyzeResponse(
        draft_id=draft_id,
        text=text,
        segments=[
            SegmentResponse(text=item.text, role=item.role, explanation=item.explanation)
            for item in analysis.segments
        ],
        patterns=[
            PatternChoiceResponse(
                index=index,
                text=item.text,
                category=item.category,
                label=item.label,
                explanation=item.explanation,
                contrast_example=f"Change or remove “{item.text}” and notice how the structure or meaning changes.",
                challenge_prompt=f"Type the construction name to confirm your choice: {item.label}",
            )
            for index, item in enumerate(patterns)
        ],
    )


@router.post(
    "/api/pattern-workshop/complete",
    response_model=SkillResponse,
    dependencies=[Depends(require_feature("pattern_workshop"))],
)
async def complete_pattern_workshop(req: CompleteRequest, username: CurrentUser) -> SkillResponse:
    now = time.time()
    _clean_expired_drafts(now)
    draft = _drafts.get(req.draft_id)
    if draft is None or draft.username != username:
        raise HTTPException(status_code=404, detail="Workshop draft not found")
    if req.pattern_index >= len(draft.patterns):
        raise HTTPException(status_code=400, detail="Unknown pattern choice")
    pattern = draft.patterns[req.pattern_index]
    if " ".join(req.answer.split()).casefold() != pattern.label.casefold():
        raise HTTPException(status_code=422, detail="Complete the micro-practice before saving")

    storage = get_storage(username)
    items = RememberGrammar().execute(
        storage.grammar.all(),
        GrammarObservation(
            language=draft.language,
            category=pattern.category,
            label=pattern.label,
            explanation=pattern.explanation,
            example=draft.text,
            source_url=draft.source_url,
        ),
        item_id=str(uuid4()),
        observed_at=now,
    )
    storage.grammar.replace_all(items)
    storage.save()
    _drafts.pop(req.draft_id, None)
    item = next(value for value in items if value.category == pattern.category and value.label == pattern.label)
    return _skill_response(item)


@router.post(
    "/api/pattern-workshop/error-drafts",
    response_model=AnalyzeResponse,
    dependencies=[Depends(require_feature("pattern_workshop"))],
)
async def create_error_draft(req: ErrorDraftRequest, username: CurrentUser) -> AnalyzeResponse:
    """Turn a learner error into a temporary workshop draft, not a saved skill."""
    storage = get_storage(username)
    now = time.time()
    _clean_expired_drafts(now)
    draft_id = uuid4().hex
    pattern = _DraftPattern(
        text=" ".join(req.correction.split()),
        category=req.category,
        label=" ".join(req.label.split()),
        explanation=" ".join(req.explanation.split()),
    )
    original = " ".join(req.original.split())
    correction = " ".join(req.correction.split())
    _drafts[draft_id] = _Draft(
        username=username,
        language=storage.settings.target_lang or "en",
        text=correction,
        source_url=f"veksha:{req.source}",
        patterns=(pattern,),
        expires_at=now + _DRAFT_TTL_SECONDS,
    )
    return AnalyzeResponse(
        draft_id=draft_id,
        text=correction,
        segments=[],
        patterns=[PatternChoiceResponse(
            index=0,
            text=pattern.text,
            category=pattern.category,
            label=pattern.label,
            explanation=pattern.explanation,
            contrast_example=f"{original} → {correction}",
            challenge_prompt=f"Type the construction name to confirm your choice: {pattern.label}",
        )],
    )


@router.get(
    "/api/pattern-workshop/skills",
    response_model=list[SkillResponse],
    dependencies=[Depends(require_feature("pattern_workshop"))],
)
async def pattern_workshop_skills(username: CurrentUser) -> list[SkillResponse]:
    storage = get_storage(username)
    language = storage.settings.target_lang or "en"
    return [_skill_response(item) for item in storage.grammar.for_language(language)]


def _skill_response(item: GrammarMemoryItem) -> SkillResponse:
    return SkillResponse(
        item_id=item.item_id,
        category=item.category,
        label=item.label,
        explanation=item.explanation,
        status=item.status,
        practice_count=item.seen_count,
    )
