import pytest
from fastapi import HTTPException

from api import subtitles as subtitles_api
from learning_core_v2.subtitles import (
    Alignment,
    SubtitleBatchTranslation,
    SubtitleLineTranslation,
)


pytestmark = pytest.mark.asyncio


class Translator:
    requests = []

    async def execute(self, request):
        self.requests.append(request)
        return SubtitleBatchTranslation(
            tuple(
                SubtitleLineTranslation(
                    (f"translated:{line[0]}",),
                    (Alignment((0,), (0,)),),
                    "en",
                )
                for line in request.lines
            )
        )


async def test_single_endpoint_sanitizes_and_maps_domain_response(monkeypatch):
    translator = Translator()
    monkeypatch.setattr(subtitles_api, "build_subtitle_translator", lambda: translator)
    request = subtitles_api.SubtitleTranslateRequest(
        tokens=[" Hello ", "there"], source_lang="auto", target_lang="ru"
    )

    response = await subtitles_api.api_subtitles_translate(request, "tester")

    assert translator.requests[0].lines == (("Hello", "there"),)
    assert response.translation_tokens == ["translated:Hello"]
    assert response.alignment[0].src == [0]
    assert response.detected_source_lang == "en"


async def test_batch_endpoint_preserves_order(monkeypatch):
    translator = Translator()
    monkeypatch.setattr(subtitles_api, "build_subtitle_translator", lambda: translator)
    request = subtitles_api.SubtitleBatchTranslateRequest(
        lines=[[" First "], ["Second"]], target_lang="ru"
    )

    response = await subtitles_api.api_subtitles_translate_batch(request, "tester")

    assert [line.translation_tokens[0] for line in response.lines] == [
        "translated:First",
        "translated:Second",
    ]


async def test_endpoint_maps_provider_failure_to_502(monkeypatch):
    class BrokenTranslator:
        async def execute(self, request):
            raise RuntimeError("unavailable")

    monkeypatch.setattr(
        subtitles_api, "build_subtitle_translator", lambda: BrokenTranslator()
    )
    request = subtitles_api.SubtitleTranslateRequest(tokens=["Hello"], target_lang="ru")

    with pytest.raises(HTTPException) as error:
        await subtitles_api.api_subtitles_translate(request, "tester")

    assert error.value.status_code == 502


async def test_batch_endpoint_rejects_empty_line():
    request = subtitles_api.SubtitleBatchTranslateRequest(
        lines=[["   "]], target_lang="ru"
    )

    with pytest.raises(HTTPException) as error:
        await subtitles_api.api_subtitles_translate_batch(request, "tester")

    assert error.value.status_code == 400
