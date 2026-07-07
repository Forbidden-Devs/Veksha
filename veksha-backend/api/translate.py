"""
api/translate.py — translation and explanation endpoints.

  POST /api/translate       — translate selection + KB patches (LLM)
  POST /api/quick_translate — translate via LLM with optional Redis cache
  POST /api/explain         — "More details" expanded explanation
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

import llm
import selection
from auth import CurrentUser
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_lang: str = "auto"
    target_lang: str = "ru"
    bidirectional: bool = False


class TranslateResponse(BaseModel):
    translation: str
    detected_source_lang: str | None = None
    single: bool
    normalized_text: str = ""


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1)
    translation: str = ""


class ExplainResponse(BaseModel):
    explanation: str


@router.post("/api/translate", response_model=TranslateResponse)
async def api_translate(req: TranslateRequest, username: CurrentUser) -> TranslateResponse:
    storage = get_storage(username)
    result = await selection.translate_and_update_kb(
        storage,
        req.text,
        req.source_lang,
        req.target_lang,
        bidirectional=req.bidirectional,
    )
    return TranslateResponse(
        translation=result["translation"],
        detected_source_lang=result.get("detected_source_lang"),
        single=result["single"],
        normalized_text=result.get("normalized_text", ""),
    )


@router.post("/api/quick_translate", response_model=TranslateResponse)
async def api_quick_translate(
    req: TranslateRequest, username: CurrentUser, background_tasks: BackgroundTasks
) -> TranslateResponse:
    """
    Translate through the LLM. One- and two-word results may be served from cache.
    """
    storage = get_storage(username)
    level = storage.settings.english_level or "intermediate"

    try:
        result = await llm.translate_selection(
            req.text,
            req.source_lang,
            req.target_lang,
            level=level,
            bidirectional=req.bidirectional,
        )
    except Exception as e:
        log.error("[quick_translate] LLM failed: %s", e)
        raise HTTPException(status_code=502, detail="Translation unavailable.")

    if result and result["translation"]:
        background_tasks.add_task(selection.update_kb_from_selection, storage, req.text, result)

    return TranslateResponse(
        translation=result["translation"],
        detected_source_lang=result.get("detected_source_lang"),
        single=result["single"],
        normalized_text=result.get("normalized_text", ""),
    )


@router.post("/api/explain", response_model=ExplainResponse)
async def api_explain(req: ExplainRequest, username: CurrentUser) -> ExplainResponse:
    storage = get_storage(username)
    explanation = await selection.explain_text(storage, req.text, req.translation)
    return ExplainResponse(explanation=explanation)
