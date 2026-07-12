"""
api/subtitles.py — dual-subtitle translation endpoint.

  POST /api/subtitles/translate — translate one subtitle line with word
                                  alignment (see llm/subtitles.py)

The extension sends the current caption line as the same whitespace tokens it
rendered as interactive spans; alignment indices refer to those tokens.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from llm.subtitles import translate_subtitle_line

log = logging.getLogger(__name__)

router = APIRouter()

MAX_TOKENS = 40
MAX_TOKEN_LENGTH = 48


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


@router.post("/api/subtitles/translate", response_model=SubtitleTranslateResponse)
async def api_subtitles_translate(
    req: SubtitleTranslateRequest, username: CurrentUser,
) -> SubtitleTranslateResponse:
    tokens = [t.strip()[:MAX_TOKEN_LENGTH] for t in req.tokens if t.strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail="tokens must not be empty")
    try:
        result = await translate_subtitle_line(tokens, req.source_lang, req.target_lang)
    except Exception as err:
        log.warning("[subtitles] translate failed for user %r: %s", username, err)
        raise HTTPException(status_code=502, detail="Subtitle translation failed.")
    return SubtitleTranslateResponse(**result)
