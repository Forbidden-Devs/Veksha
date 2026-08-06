"""Authenticated Veksha speech boundary backed by Speech Platform."""
from __future__ import annotations

import io
import logging
from typing import Annotated, Literal

import aiohttp
import db
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import CurrentUser
from config import (
    SPEECH_BASE_URL,
    SPEECH_DEFAULT_VOICE_ID,
    SPEECH_SHARED_SECRET,
    SPEECH_TIMEOUT_SECONDS,
)
from speech_client import (
    SpeechPlatformClient,
    SpeechPlatformError,
    SpeechUsage,
    SynthesisRequest,
    TranscriptionResult,
)


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/speech", tags=["speech"])
_MAX_WAV_BYTES = 10 * 1024 * 1024


class SynthesizeBody(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: str = Field(pattern=r"^[A-Za-z]{2,3}$")
    operation_id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9._:-]+$")
    quality: Literal["fast", "balanced", "quality"] = "balanced"


class TranscriptWordResponse(BaseModel):
    text: str
    start: float
    end: float
    speaker: str | None = None


class TranscriptResponse(BaseModel):
    text: str
    language: str | None = None
    language_confidence: float | None = None
    words: list[TranscriptWordResponse] = Field(default_factory=list)


def _client(*, require_voice: bool = False) -> SpeechPlatformClient:
    if not SPEECH_SHARED_SECRET or (require_voice and not SPEECH_DEFAULT_VOICE_ID):
        raise HTTPException(status_code=503, detail="Speech is not configured.")
    return SpeechPlatformClient(
        SPEECH_BASE_URL,
        SPEECH_SHARED_SECRET,
        SPEECH_DEFAULT_VOICE_ID,
        SPEECH_TIMEOUT_SECONDS,
    )


def _record_usage(
    username: str,
    operation: str,
    usage: SpeechUsage,
    *,
    counted_audio_bytes: int = 0,
) -> None:
    try:
        db.speech_usage_record(
            username=username,
            operation=operation,
            request_id=usage.request_id,
            provider=usage.provider,
            model=usage.model,
            characters=usage.characters,
            audio_bytes=usage.audio_bytes or counted_audio_bytes,
            provider_request_id=usage.provider_request_id,
        )
    except Exception:
        log.exception(
            "Failed to persist speech usage: operation=%s request_id=%s",
            operation,
            usage.request_id or "missing",
        )


def _raise_platform_error(error: SpeechPlatformError) -> None:
    log.warning(
        "Speech Platform request failed: status=%s code=%s request_id=%s",
        error.status,
        error.code,
        error.request_id or "missing",
    )
    status = error.status if error.status in {400, 422, 429} else 503
    raise HTTPException(
        status_code=status,
        detail={"code": error.code, "message": error.message, "request_id": error.request_id},
    ) from error


@router.post("/synthesize", response_class=StreamingResponse)
async def synthesize(body: SynthesizeBody, username: CurrentUser) -> StreamingResponse:
    try:
        audio = await _client(require_voice=True).synthesize(SynthesisRequest(
            text=body.text,
            language=body.language.lower(),
            operation_id=body.operation_id,
            quality=body.quality,
        ))
    except SpeechPlatformError as error:
        _raise_platform_error(error)
    except (aiohttp.ClientError, TimeoutError) as error:
        log.warning("Speech Platform TTS unavailable: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Speech is temporarily unavailable.") from error
    if audio.request_id:
        log.info("Speech Platform TTS started: request_id=%s", audio.request_id)

    async def stream():
        received = 0
        try:
            async for chunk in audio.chunks():
                received += len(chunk)
                yield chunk
        finally:
            _record_usage(username, "tts", audio.usage, counted_audio_bytes=received)

    return StreamingResponse(
        stream(),
        media_type=audio.content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(
    audio: Annotated[UploadFile, File()],
    operation_id: Annotated[str, Form(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9._:-]+$")],
    username: CurrentUser,
    language: Annotated[str | None, Form(pattern=r"^[A-Za-z]{2,3}$")] = None,
) -> TranscriptResponse:
    if audio.content_type not in {"audio/wav", "audio/wave", "audio/x-wav"}:
        raise HTTPException(status_code=415, detail="A PCM WAV recording is required.")
    payload = await audio.read(_MAX_WAV_BYTES + 1)
    if not payload or len(payload) > _MAX_WAV_BYTES:
        raise HTTPException(status_code=413, detail="Recording is empty or too large.")
    try:
        result: TranscriptionResult = await _client().transcribe(
            io.BytesIO(payload),
            audio.filename or "recording.wav",
            operation_id,
            language.lower() if language else None,
        )
    except SpeechPlatformError as error:
        _raise_platform_error(error)
    except (aiohttp.ClientError, TimeoutError) as error:
        log.warning("Speech Platform STT unavailable: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Transcription is temporarily unavailable.") from error
    _record_usage(username, "stt", result.usage, counted_audio_bytes=len(payload))
    transcript = result.transcript
    return TranscriptResponse(
        text=transcript.text,
        language=transcript.language,
        language_confidence=transcript.language_confidence,
        words=[TranscriptWordResponse(
            text=word.text,
            start=word.start,
            end=word.end,
            speaker=word.speaker,
        ) for word in transcript.words],
    )
