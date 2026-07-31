"""Grammar Memory API — analyze text and retain recurring grammar patterns."""
from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from entitlements import require_feature
from learning_core_v2.grammar_memory import (
    GrammarMemoryItem,
    GrammarObservation,
    RememberGrammar,
    SetGrammarStatus,
)
from llm.grammar_lens import analyze_grammar_block
from storage import get_storage

router = APIRouter()

_MIN_BLOCK_CHARS = 18
_MAX_BLOCK_CHARS = 6000
_MAX_BLOCKS = 48
_CONCURRENCY = 6


class GrammarLensRequest(BaseModel):
    blocks: list[str] = Field(default_factory=list)
    source_url: str = Field("", max_length=2000)


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
    remembered: int = 0


class GrammarMemoryEncounterResponse(BaseModel):
    example: str
    source_url: str
    observed_at: float


class GrammarMemoryItemResponse(BaseModel):
    item_id: str
    category: str
    label: str
    explanation: str
    status: str
    seen_count: int
    first_seen_at: float
    last_seen_at: float
    encounters: list[GrammarMemoryEncounterResponse]


class GrammarMemoryResponse(BaseModel):
    items: list[GrammarMemoryItemResponse]


class GrammarMemoryStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(learning|mastered)$")


@router.post(
    "/api/grammar-lens/analyze",
    response_model=GrammarLensResponse,
    dependencies=[Depends(require_feature("grammar_lens"))],
)
async def api_grammar_lens_analyze(
    req: GrammarLensRequest,
    username: CurrentUser,
) -> GrammarLensResponse:
    storage = get_storage(username)
    settings = storage.settings
    native_lang = settings.native_lang or "en"
    learner_level = settings.english_level or "unknown"
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def run(text: str) -> GrammarBlock:
        if len((text or "").strip()) < _MIN_BLOCK_CHARS:
            return GrammarBlock()
        text = text[:_MAX_BLOCK_CHARS]
        async with semaphore:
            analysis = await analyze_grammar_block(text, native_lang, learner_level)
        return GrammarBlock(
            segments=[GrammarSegment(**item) for item in analysis["segments"]],
            annotations=[GrammarAnnotation(**item) for item in analysis["annotations"]],
        )

    source_blocks = req.blocks[:_MAX_BLOCKS]
    blocks = await asyncio.gather(*(run(text) for text in source_blocks))
    memory = list(storage.grammar_memory)
    remember = RememberGrammar()
    observed_at = time.time()
    for source, block in zip(source_blocks, blocks, strict=True):
        example = " ".join(source.split())[:1000]
        for annotation in block.annotations:
            try:
                memory = list(
                    remember.execute(
                        memory,
                        GrammarObservation(
                            language=settings.target_lang or "en",
                            category=annotation.category,
                            label=annotation.label,
                            explanation=annotation.explanation,
                            example=example,
                            source_url=req.source_url,
                        ),
                        item_id=str(uuid.uuid4()),
                        observed_at=observed_at,
                    )
                )
            except ValueError:
                continue
    if memory != storage.grammar_memory:
        storage.grammar_memory = memory
        storage.save()
    return GrammarLensResponse(blocks=list(blocks), remembered=len(memory))


@router.get(
    "/api/grammar-memory",
    response_model=GrammarMemoryResponse,
    dependencies=[Depends(require_feature("grammar_lens"))],
)
async def api_grammar_memory(username: CurrentUser) -> GrammarMemoryResponse:
    storage = get_storage(username)
    language = storage.settings.target_lang or "en"
    items = sorted(
        (item for item in storage.grammar_memory if item.language == language),
        key=lambda item: (item.status == "mastered", -item.last_seen_at, -item.seen_count),
    )
    return GrammarMemoryResponse(items=[_memory_response(item) for item in items])


@router.post(
    "/api/grammar-memory/{item_id}/status",
    response_model=GrammarMemoryItemResponse,
    dependencies=[Depends(require_feature("grammar_lens"))],
)
async def api_grammar_memory_status(
    item_id: str,
    req: GrammarMemoryStatusRequest,
    username: CurrentUser,
) -> GrammarMemoryItemResponse:
    storage = get_storage(username)
    index = next(
        (index for index, item in enumerate(storage.grammar_memory) if item.item_id == item_id),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Grammar memory item not found")
    updated = SetGrammarStatus().execute(storage.grammar_memory[index], req.status)
    storage.grammar_memory[index] = updated
    storage.save()
    return _memory_response(updated)


def _memory_response(item: GrammarMemoryItem) -> GrammarMemoryItemResponse:
    return GrammarMemoryItemResponse(
        item_id=item.item_id,
        category=item.category,
        label=item.label,
        explanation=item.explanation,
        status=item.status,
        seen_count=item.seen_count,
        first_seen_at=item.first_seen_at,
        last_seen_at=item.last_seen_at,
        encounters=[
            GrammarMemoryEncounterResponse(
                example=encounter.example,
                source_url=encounter.source_url,
                observed_at=encounter.observed_at,
            )
            for encounter in reversed(item.encounters)
        ],
    )
