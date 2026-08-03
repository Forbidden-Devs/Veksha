"""Translation HTTP adapter backed by the independently rewritten core-v2."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from learning_core_v2.explanation import ExplanationRequest
from learning_core_v2.translation import TranslationRequest
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import (
    build_deferred_translate_text,
    build_explain_text,
    build_translate_text,
)
from storage import get_storage


log = logging.getLogger(__name__)
router = APIRouter()


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_lang: str = "auto"
    target_lang: str = "ru"
    bidirectional: bool = False
    source_url: str = Field("", max_length=2000)


class TranslateResponse(BaseModel):
    translation: str
    detected_source_lang: str | None = None
    single: bool
    normalized_text: str = ""
    vocabulary_mode: Literal["saved", "suggested"] = "saved"


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1)
    translation: str = ""


class ExplainResponse(BaseModel):
    explanation: str


async def _execute_translation(req: TranslateRequest, storage, service) -> TranslateResponse:
    source_language = req.source_lang
    target_language = req.target_lang
    if req.bidirectional:
        source_language = storage.settings.native_lang or source_language
        target_language = storage.settings.target_lang or target_language
    try:
        result = await service.execute(
            TranslationRequest(
                text=req.text,
                source_language=source_language,
                target_language=target_language,
                proficiency=storage.settings.english_level or "intermediate",
                bidirectional=req.bidirectional,
                source_url=req.source_url,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LanguageProviderError as exc:
        log.warning("core-v2 translation unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Translation unavailable.") from exc

    return TranslateResponse(
        translation=result.translation,
        detected_source_lang=result.detected_source_language,
        single=result.is_lexical_unit,
        normalized_text=result.dictionary_form,
        vocabulary_mode="suggested",
    )


async def _translate(req: TranslateRequest, username: str) -> TranslateResponse:
    storage = get_storage(username)
    return await _execute_translation(req, storage, build_translate_text(storage))


@router.post("/api/translate", response_model=TranslateResponse)
async def api_translate(req: TranslateRequest, username: CurrentUser) -> TranslateResponse:
    return await _translate(req, username)


@router.post("/api/quick_translate", response_model=TranslateResponse)
async def api_quick_translate(
    req: TranslateRequest,
    username: CurrentUser,
    background_tasks: BackgroundTasks,
) -> TranslateResponse:
    storage = get_storage(username)
    service, collector, target = build_deferred_translate_text(storage)
    response = await _execute_translation(req, storage, service)
    for observation in collector.observations:
        background_tasks.add_task(target.observe, observation)
    return response


@router.post("/api/explain", response_model=ExplainResponse)
async def api_explain(req: ExplainRequest, username: CurrentUser) -> ExplainResponse:
    storage = get_storage(username)
    try:
        result = await build_explain_text().execute(
            ExplanationRequest(
                text=req.text,
                translation=req.translation,
                proficiency=storage.settings.english_level or "intermediate",
                native_language=storage.settings.native_lang or "en",
                learning_language=storage.settings.target_lang or "en",
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LanguageProviderError as exc:
        log.warning("core-v2 explanation unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Explanation unavailable.") from exc
    return ExplainResponse(explanation=result.explanation)
