"""
api/stt.py - microphone speech-to-text endpoint.

The browser records audio locally and sends a short webm clip here. The backend
keeps the OpenAI API key private and forwards the audio to OpenAI transcription.
"""
from __future__ import annotations

import logging

import aiohttp
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from auth import CurrentUser
from config import OPENAI_API_KEY, OPENAI_STT_FALLBACK_MODEL, OPENAI_STT_MODEL

log = logging.getLogger(__name__)

router = APIRouter()

_OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


class STTResponse(BaseModel):
    text: str


@router.post("/api/stt", response_model=STTResponse)
@router.post("/stt/", response_model=STTResponse)
async def api_stt(
    _username: CurrentUser,
    file: UploadFile = File(...),
    language: str = Form(""),
    language_header: str = Header("", alias="X-Veksha-STT-Language"),
) -> STTResponse:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured.")

    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is too large.")

    language_hint = (language or language_header).strip().lower().split("-", 1)[0].split("_", 1)[0]
    log.info("[stt] received language hint=%r", language_hint or None)

    models = [OPENAI_STT_MODEL]
    if OPENAI_STT_FALLBACK_MODEL and OPENAI_STT_FALLBACK_MODEL not in models:
        models.append(OPENAI_STT_FALLBACK_MODEL)

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    async with aiohttp.ClientSession() as session:
        for index, model in enumerate(models):
            try:
                data = await _transcribe(session, headers, audio, file, language_hint, model)
                return STTResponse(text=(data.get("text") or "").strip())
            except _STTModelUnavailable as exc:
                if index + 1 >= len(models):
                    log.error("[stt] model unavailable and no fallback left: %s", exc)
                    raise HTTPException(status_code=502, detail="STT model unavailable.") from exc
                log.warning("[stt] model %s unavailable, retrying with %s", model, models[index + 1])
            except HTTPException:
                raise
            except Exception as exc:
                log.error("[stt] request failed: %s", exc, exc_info=True)
                raise HTTPException(status_code=502, detail="STT service unavailable.") from exc

    raise HTTPException(status_code=502, detail="STT service unavailable.")


class _STTModelUnavailable(Exception):
    pass


async def _transcribe(
    session: aiohttp.ClientSession,
    headers: dict[str, str],
    audio: bytes,
    file: UploadFile,
    language: str,
    model: str,
) -> dict:
    form = aiohttp.FormData()
    form.add_field(
        "file",
        audio,
        filename=file.filename or "speech.webm",
        content_type=file.content_type or "audio/webm",
    )
    form.add_field("model", model)
    form.add_field("response_format", "json")
    if language and language != "auto":
        form.add_field("language", language)

    async with session.post(_OPENAI_TRANSCRIPTIONS_URL, data=form, headers=headers) as res:
        body = await res.text()
        if res.status == 404:
            raise _STTModelUnavailable(f"{model}: {body[:500]}")
        if res.status >= 400:
            log.error("[stt] OpenAI model=%s HTTP %d: %s", model, res.status, body[:1000])
            raise HTTPException(status_code=502, detail="STT service unavailable.")
        return await res.json(content_type=None)
