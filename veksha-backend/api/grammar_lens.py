"""Grammar Lens API — identify grammatical roles in visible page text."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import llm
from auth import CurrentUser
from entitlements import require_feature
from storage import get_storage

router = APIRouter()

_MIN_BLOCK_CHARS = 18
_MAX_BLOCK_CHARS = 6000
_MAX_BLOCKS = 48
_CONCURRENCY = 6


class GrammarLensRequest(BaseModel):
    blocks: list[str] = Field(default_factory=list)


class GrammarSegment(BaseModel):
    text: str
    role: str
    explanation: str = ""


class GrammarAnnotation(BaseModel):
    text: str
    category: str
    label: str
    explanation: str = ""


class GrammarBlock(BaseModel):
    segments: list[GrammarSegment] = Field(default_factory=list)
    annotations: list[GrammarAnnotation] = Field(default_factory=list)


class GrammarLensResponse(BaseModel):
    blocks: list[GrammarBlock]


@router.post(
    "/api/grammar-lens/analyze",
    response_model=GrammarLensResponse,
    dependencies=[Depends(require_feature("grammar_lens"))],
)
async def api_grammar_lens_analyze(
    req: GrammarLensRequest,
    username: CurrentUser,
) -> GrammarLensResponse:
    settings = get_storage(username).settings
    native_lang = settings.native_lang or "en"
    learner_level = settings.english_level or "unknown"
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def run(text: str) -> GrammarBlock:
        if len((text or "").strip()) < _MIN_BLOCK_CHARS:
            return GrammarBlock()
        text = text[:_MAX_BLOCK_CHARS]
        async with semaphore:
            analysis = await llm.analyze_grammar_block(text, native_lang, learner_level)
        return GrammarBlock(
            segments=[GrammarSegment(**item) for item in analysis["segments"]],
            annotations=[GrammarAnnotation(**item) for item in analysis["annotations"]],
        )

    blocks = await asyncio.gather(*(run(text) for text in req.blocks[:_MAX_BLOCKS]))
    return GrammarLensResponse(blocks=list(blocks))
