"""
api/subtitles.py — dual-subtitle translation endpoint.

  POST /api/subtitles/translate       — translate one subtitle line with alignment
  POST /api/subtitles/translate-batch — pretranslate adjacent timed cues

Alignment indices always refer to the whitespace tokens submitted for that cue.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from entitlements import require_feature
from learning_core_v2.subtitles import SubtitleTranslationRequest
from learning_core_v2_adapters.runtime import build_subtitle_translator

log = logging.getLogger(__name__)

router = APIRouter()

MAX_TOKENS = 40
MAX_TOKEN_LENGTH = 48
MAX_BATCH_LINES = 12


class SubtitleTranslateRequest(BaseModel):
    tokens: list[str] = Field(..., min_length=1, max_length=MAX_TOKENS)
    source_lang: str = "auto"
    target_lang: str = Field(..., min_length=2, max_length=8)


class AlignmentGroup(BaseModel):
    src: list[int]
    dst: list[int]


class SubtitleTranslateResponse(BaseModel):
    translation_tokens: list[str]
    alignment: list[AlignmentGroup]
    detected_source_lang: str | None = None


class SubtitleBatchTranslateRequest(BaseModel):
    lines: list[list[str]] = Field(..., min_length=1, max_length=MAX_BATCH_LINES)
    source_lang: str = "auto"
    target_lang: str = Field(..., min_length=2, max_length=8)


class SubtitleBatchTranslateResponse(BaseModel):
    lines: list[SubtitleTranslateResponse]


@router.post(
    "/api/subtitles/translate",
    response_model=SubtitleTranslateResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def api_subtitles_translate(
    req: SubtitleTranslateRequest, username: CurrentUser,
) -> SubtitleTranslateResponse:
    tokens = [t.strip()[:MAX_TOKEN_LENGTH] for t in req.tokens if t.strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail="tokens must not be empty")
    try:
        result = await build_subtitle_translator().execute(
            SubtitleTranslationRequest(
                (tuple(tokens),), req.source_lang, req.target_lang
            )
        )
    except Exception as err:
        log.warning("[subtitles] translate failed for user %r: %s", username, err)
        raise HTTPException(status_code=502, detail="Subtitle translation failed.")
    return _response(result.lines[0])


@router.post(
    "/api/subtitles/translate-batch",
    response_model=SubtitleBatchTranslateResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def api_subtitles_translate_batch(
    req: SubtitleBatchTranslateRequest, username: CurrentUser,
) -> SubtitleBatchTranslateResponse:
    lines = [
        [token.strip()[:MAX_TOKEN_LENGTH] for token in line if token.strip()]
        for line in req.lines
    ]
    if any(not line for line in lines):
        raise HTTPException(status_code=400, detail="subtitle lines must not be empty")
    if any(len(line) > MAX_TOKENS for line in lines):
        raise HTTPException(status_code=400, detail=f"each line may contain at most {MAX_TOKENS} tokens")
    try:
        result = await build_subtitle_translator().execute(
            SubtitleTranslationRequest(
                tuple(tuple(line) for line in lines), req.source_lang, req.target_lang
            )
        )
    except Exception as err:
        log.warning("[subtitles] batch translate failed for user %r: %s", username, err)
        raise HTTPException(status_code=502, detail="Subtitle batch translation failed.")
    return SubtitleBatchTranslateResponse(
        lines=[_response(line) for line in result.lines],
    )


def _response(line) -> SubtitleTranslateResponse:
    return SubtitleTranslateResponse(
        translation_tokens=list(line.translation_tokens),
        alignment=[
            AlignmentGroup(
                src=list(group.source_indices), dst=list(group.translation_indices)
            )
            for group in line.alignment
        ],
        detected_source_lang=line.detected_source_language,
    )
