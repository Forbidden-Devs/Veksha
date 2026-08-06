"""Provider-neutral HTTP client for Speech Platform.

This is the only Veksha module that knows the platform transport contract.
Provider credentials, model names and provider-native payloads stay behind it.
"""
from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from typing import AsyncIterator, BinaryIO, Literal, Protocol

import aiohttp


Quality = Literal["fast", "balanced", "quality"]
AudioFormat = Literal[
    "mp3_44100_128", "mp3_22050_32", "pcm_16000", "pcm_24000", "ulaw_8000"
]
_RETRYABLE_STATUSES = frozenset({429, 502, 503})


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    text: str
    language: str
    operation_id: str
    quality: Quality = "balanced"
    format: AudioFormat = "mp3_44100_128"


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    text: str
    start: float
    end: float
    speaker: str | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str | None = None
    language_confidence: float | None = None
    words: tuple[TranscriptWord, ...] = ()


@dataclass(frozen=True, slots=True)
class SpeechUsage:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    characters: int = 0
    audio_bytes: int = 0
    provider_request_id: str = ""


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    transcript: Transcript
    usage: SpeechUsage


class SpeechPlatformError(Exception):
    def __init__(self, status: int, code: str, message: str, request_id: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id


class SpeechAudio:
    """A live platform response whose body can be forwarded without buffering."""

    def __init__(self, session: aiohttp.ClientSession, response: aiohttp.ClientResponse) -> None:
        self._session = session
        self._response = response
        self.content_type = response.headers.get("Content-Type", "audio/mpeg").split(";", 1)[0]
        self.usage = _response_usage(response)

    @property
    def request_id(self) -> str:
        return self.usage.request_id

    async def chunks(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.content.iter_chunked(64 * 1024):
                yield chunk
        finally:
            await self.close()

    async def close(self) -> None:
        self._response.close()
        if not self._session.closed:
            await self._session.close()


class SpeechClient(Protocol):
    async def synthesize(self, request: SynthesisRequest) -> SpeechAudio: ...

    async def transcribe(
        self,
        audio: BinaryIO,
        filename: str,
        operation_id: str,
        language: str | None = None,
    ) -> TranscriptionResult: ...


class SpeechPlatformClient:
    def __init__(
        self,
        base_url: str,
        shared_secret: str,
        default_voice_id: str,
        timeout_seconds: float = 60.0,
        max_attempts: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._shared_secret = shared_secret
        self._default_voice_id = default_voice_id
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._max_attempts = max(1, max_attempts)

    def _headers(self, operation_id: str, kind: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._shared_secret}",
            "Idempotency-Key": f"veksha-{kind}-{operation_id}"[:128],
        }

    async def synthesize(self, request: SynthesisRequest) -> SpeechAudio:
        payload = {
            "text": request.text,
            "voice_id": self._default_voice_id,
            "language": request.language,
            "quality": request.quality,
            "format": request.format,
        }
        for attempt in range(self._max_attempts):
            session = aiohttp.ClientSession(timeout=self._timeout)
            try:
                response = await session.post(
                    f"{self._base_url}/v1/speech",
                    headers={**self._headers(request.operation_id, "tts"), "Content-Type": "application/json"},
                    json=payload,
                )
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await session.close()
                if attempt + 1 >= self._max_attempts:
                    raise
                await self._backoff(attempt)
                continue
            if response.status < 400:
                return SpeechAudio(session, response)
            error = await self._platform_error(response)
            response.close()
            await session.close()
            if error.status not in _RETRYABLE_STATUSES or attempt + 1 >= self._max_attempts:
                raise error
            await self._backoff(attempt)
        raise RuntimeError("unreachable")

    async def transcribe(
        self,
        audio: BinaryIO,
        filename: str,
        operation_id: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        body = audio.read()
        for attempt in range(self._max_attempts):
            form = aiohttp.FormData()
            form.add_field("audio", io.BytesIO(body), filename=filename, content_type="audio/wav")
            if language:
                form.add_field("language", language)
            try:
                async with aiohttp.ClientSession(timeout=self._timeout) as session:
                    async with session.post(
                        f"{self._base_url}/v1/transcriptions",
                        headers=self._headers(operation_id, "stt"),
                        data=form,
                    ) as response:
                        if response.status >= 400:
                            error = await self._platform_error(response)
                            if error.status in _RETRYABLE_STATUSES and attempt + 1 < self._max_attempts:
                                await self._backoff(attempt)
                                continue
                            raise error
                        payload = await response.json(content_type=None)
                        usage = _response_usage(response)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt + 1 >= self._max_attempts:
                    raise
                await self._backoff(attempt)
                continue
            return TranscriptionResult(self._parse_transcript(payload), usage)
        raise RuntimeError("unreachable")

    @staticmethod
    async def _platform_error(response: aiohttp.ClientResponse) -> SpeechPlatformError:
        try:
            payload = json.loads(await response.text())
            detail = payload["error"]
            return SpeechPlatformError(
                response.status,
                str(detail.get("code") or "speech_platform_error"),
                str(detail.get("message") or "Speech request failed"),
                str(detail.get("request_id") or response.headers.get("X-Request-ID") or ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            return SpeechPlatformError(
                response.status,
                "speech_platform_error",
                "Speech request failed",
                response.headers.get("X-Request-ID", ""),
            )

    @staticmethod
    def _parse_transcript(payload: object) -> Transcript:
        if not isinstance(payload, dict) or not isinstance(payload.get("transcript"), dict):
            raise SpeechPlatformError(502, "invalid_response", "Speech Platform returned an invalid transcript")
        transcript = payload["transcript"]
        words = tuple(
            TranscriptWord(
                text=str(word.get("text") or ""),
                start=float(word.get("start") or 0),
                end=float(word.get("end") or 0),
                speaker=str(word["speaker"]) if word.get("speaker") is not None else None,
            )
            for word in transcript.get("words") or []
            if isinstance(word, dict)
        )
        confidence = transcript.get("language_confidence")
        return Transcript(
            text=str(transcript.get("text") or ""),
            language=str(transcript["language"]) if transcript.get("language") is not None else None,
            language_confidence=float(confidence) if confidence is not None else None,
            words=words,
        )

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(0.25 * (2**attempt))


def _response_usage(response: aiohttp.ClientResponse) -> SpeechUsage:
    def integer(name: str) -> int:
        try:
            return max(0, int(response.headers.get(name, "0")))
        except (TypeError, ValueError):
            return 0

    return SpeechUsage(
        request_id=response.headers.get("X-Request-ID", ""),
        provider=response.headers.get("X-Speech-Provider", ""),
        model=response.headers.get("X-Speech-Model", ""),
        characters=integer("X-Speech-Characters"),
        audio_bytes=integer("X-Speech-Audio-Bytes"),
        provider_request_id=response.headers.get("X-Speech-Provider-Request-ID", ""),
    )
