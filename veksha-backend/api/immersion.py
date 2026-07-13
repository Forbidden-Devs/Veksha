"""
api/immersion.py — "comprehensible input" page immersion.

  POST /api/immersion/analyze — split visible page text into sentences, rate
  each (CEFR), translate only the i+1 ones into the studied language.

The client sends the text of the page blocks currently in view; language pair
and level are taken from the user's settings. Per-block results are cached in
llm.immersion so scrolling back and revisiting pages is instant.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import llm
from auth import CurrentUser
from cefr import LEVEL_TO_CEFR as _LEVEL_TO_CEFR
from entitlements import require_feature
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()

# Don't bother the LLM with tiny fragments (labels, single words).
_MIN_BLOCK_CHARS = 30
_MAX_BLOCKS = 60
_CONCURRENCY = 6


class ImmersionRequest(BaseModel):
    blocks: list[str] = Field(default_factory=list)


class ImmersionSentence(BaseModel):
    text: str
    cefr: str = ""
    translation: str = ""


class ImmersionBlock(BaseModel):
    sentences: list[ImmersionSentence] = Field(default_factory=list)


class ImmersionResponse(BaseModel):
    blocks: list[ImmersionBlock]


@router.post(
    "/api/immersion/analyze",
    response_model=ImmersionResponse,
    dependencies=[Depends(require_feature("immersion"))],
)
async def api_immersion_analyze(req: ImmersionRequest, username: CurrentUser) -> ImmersionResponse:
    storage = get_storage(username)
    s = storage.settings
    native = s.native_lang or "en"
    target = s.target_lang or "en"
    level = _LEVEL_TO_CEFR.get(s.english_level or "intermediate", "B1")

    blocks = req.blocks[:_MAX_BLOCKS]
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def run(text: str) -> ImmersionBlock:
        if len((text or "").strip()) < _MIN_BLOCK_CHARS or native == target:
            return ImmersionBlock(sentences=[])
        async with sem:
            sentences = await llm.analyze_block(text, native, target, level)
        return ImmersionBlock(sentences=[ImmersionSentence(**s) for s in sentences])

    result = await asyncio.gather(*(run(b) for b in blocks))
    return ImmersionResponse(blocks=list(result))
