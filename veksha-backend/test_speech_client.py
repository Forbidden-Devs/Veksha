from __future__ import annotations

import io
import json
from collections.abc import Iterator

import pytest

import speech_client
from api import speech as speech_api
from speech_client import SpeechPlatformClient, SpeechPlatformError, SynthesisRequest


class FakeContent:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks

    async def iter_chunked(self, _size: int):
        for chunk in self._chunks:
            yield chunk


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        *,
        chunks: tuple[bytes, ...] = (),
        payload: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self.content = FakeContent(chunks)
        self.payload = payload
        self.closed = False

    async def text(self) -> str:
        return json.dumps(self.payload)

    async def json(self, *, content_type=None) -> object:
        return self.payload

    def close(self) -> None:
        self.closed = True


class FakeRequest:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def __await__(self) -> Iterator[FakeResponse]:
        async def result() -> FakeResponse:
            return self.response
        return result().__await__()

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *_args) -> None:
        self.response.close()


class FakeSessions:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def factory(self, *, timeout):
        owner = self

        class Session:
            closed = False

            def post(self, url: str, **kwargs) -> FakeRequest:
                owner.calls.append((url, kwargs))
                return FakeRequest(next(owner.responses))

            async def close(self) -> None:
                self.closed = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args) -> None:
                await self.close()

        return Session()


def install_sessions(monkeypatch, responses: list[FakeResponse]) -> FakeSessions:
    sessions = FakeSessions(responses)
    monkeypatch.setattr(speech_client.aiohttp, "ClientSession", sessions.factory)
    return sessions


@pytest.mark.asyncio
async def test_synthesize_uses_project_auth_stable_key_and_streams_binary(monkeypatch) -> None:
    sessions = install_sessions(monkeypatch, [FakeResponse(
        chunks=(b"mp3-", b"bytes"),
        headers={
            "Content-Type": "audio/mpeg",
            "X-Request-ID": "req_ok",
            "X-Speech-Provider": "elevenlabs",
            "X-Speech-Model": "eleven_flash_v2_5",
            "X-Speech-Characters": "5",
            "X-Speech-Provider-Request-ID": "provider_req",
        },
    )])
    client = SpeechPlatformClient("http://speech", "sp_test", "voice_tutor", max_attempts=1)
    audio = await client.synthesize(SynthesisRequest("Hello", "en", "lesson-42"))
    received = b"".join([chunk async for chunk in audio.chunks()])

    assert received == b"mp3-bytes"
    assert audio.request_id == "req_ok"
    assert audio.usage.provider == "elevenlabs"
    assert audio.usage.model == "eleven_flash_v2_5"
    assert audio.usage.characters == 5
    assert audio.usage.provider_request_id == "provider_req"
    url, call = sessions.calls[0]
    assert url == "http://speech/v1/speech"
    assert call["headers"] == {
        "Authorization": "Bearer sp_test",
        "Idempotency-Key": "veksha-tts-lesson-42",
        "Content-Type": "application/json",
    }
    assert call["json"] == {
        "text": "Hello",
        "voice_id": "voice_tutor",
        "language": "en",
        "quality": "balanced",
        "format": "mp3_44100_128",
    }


@pytest.mark.asyncio
async def test_synthesize_retries_retryable_envelope_before_stream(monkeypatch) -> None:
    failures = [FakeResponse(
        503,
        payload={"error": {"code": "provider_unavailable", "message": "try later", "request_id": f"req_{n}"}},
    ) for n in (1, 2)]
    sessions = install_sessions(monkeypatch, [*failures, FakeResponse(chunks=(b"ok",))])

    async def no_wait(_attempt: int) -> None:
        return None

    monkeypatch.setattr(SpeechPlatformClient, "_backoff", staticmethod(no_wait))
    client = SpeechPlatformClient("http://speech", "sp_test", "voice_tutor")
    audio = await client.synthesize(SynthesisRequest("Hello", "en", "same-op"))

    assert b"".join([chunk async for chunk in audio.chunks()]) == b"ok"
    assert len(sessions.calls) == 3
    assert {call[1]["headers"]["Idempotency-Key"] for call in sessions.calls} == {"veksha-tts-same-op"}


@pytest.mark.asyncio
async def test_synthesize_preserves_non_retryable_platform_error(monkeypatch) -> None:
    install_sessions(monkeypatch, [FakeResponse(
        422,
        payload={"error": {"code": "unsupported_language", "message": "not available", "request_id": "req_bad"}},
    )])
    client = SpeechPlatformClient("http://speech", "sp_test", "voice_tutor")
    with pytest.raises(SpeechPlatformError) as caught:
        await client.synthesize(SynthesisRequest("Hej", "sv", "op"))

    assert caught.value.status == 422
    assert caught.value.code == "unsupported_language"
    assert caught.value.request_id == "req_bad"


@pytest.mark.asyncio
async def test_transcribe_returns_only_normalized_transcript(monkeypatch) -> None:
    sessions = install_sessions(monkeypatch, [FakeResponse(
        payload={
            "transcript": {
                "text": "Hello",
                "language": "en",
                "language_confidence": 0.98,
                "words": [{"text": "Hello", "start": 0.1, "end": 0.5}],
            },
            "provider": "diagnostic-provider",
            "model": "diagnostic-model",
        },
        headers={
            "X-Request-ID": "req_stt",
            "X-Speech-Provider": "elevenlabs",
            "X-Speech-Model": "scribe_v2",
            "X-Speech-Characters": "5",
            "X-Speech-Audio-Bytes": "8",
        },
    )])
    client = SpeechPlatformClient("http://speech", "sp_test", "voice_tutor", max_attempts=1)
    result = await client.transcribe(io.BytesIO(b"RIFF-wav"), "recording.wav", "turn-7", "en")

    assert result.transcript.text == "Hello"
    assert result.transcript.language == "en"
    assert result.transcript.language_confidence == 0.98
    assert result.transcript.words[0].text == "Hello"
    assert result.usage.request_id == "req_stt"
    assert result.usage.audio_bytes == 8
    url, call = sessions.calls[0]
    assert url == "http://speech/v1/transcriptions"
    assert call["headers"] == {
        "Authorization": "Bearer sp_test",
        "Idempotency-Key": "veksha-stt-turn-7",
    }
    fields = {field[0]["name"]: field for field in call["data"]._fields}
    assert fields["audio"][0]["filename"] == "recording.wav"
    assert fields["language"][2] == "en"


@pytest.mark.asyncio
async def test_backend_counts_streamed_tts_bytes_and_attributes_user(monkeypatch) -> None:
    class Audio:
        request_id = "req_stream"
        content_type = "audio/mpeg"
        usage = speech_client.SpeechUsage(
            request_id="req_stream",
            provider="elevenlabs",
            model="eleven_flash_v2_5",
            characters=5,
        )

        async def chunks(self):
            yield b"one"
            yield b"two-two"

    class Client:
        async def synthesize(self, _request):
            return Audio()

    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(speech_api, "_client", lambda **_kwargs: Client())
    monkeypatch.setattr(speech_api.db, "speech_usage_record", lambda **kwargs: recorded.append(kwargs))

    response = await speech_api.synthesize(
        speech_api.SynthesizeBody(text="Hello", language="en", operation_id="lesson-1"),
        "user-1",
    )
    body = b"".join([chunk async for chunk in response.body_iterator])

    assert body == b"onetwo-two"
    assert recorded == [{
        "username": "user-1",
        "operation": "tts",
        "request_id": "req_stream",
        "provider": "elevenlabs",
        "model": "eleven_flash_v2_5",
        "characters": 5,
        "audio_bytes": 10,
        "provider_request_id": "",
    }]
