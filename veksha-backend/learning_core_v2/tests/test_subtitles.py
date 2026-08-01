import pytest

from learning_core_v2.subtitles import (
    AlignmentDraft,
    SubtitleLineDraft,
    SubtitleTranslationRequest,
    TranslateSubtitles,
)


pytestmark = pytest.mark.asyncio


class Provider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def translate_subtitles(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def test_alignment_is_bounded_unique_and_ordered():
    provider = Provider(
        [
            (
                SubtitleLineDraft(
                    index=0,
                    translation_tokens=("Я", "знаю"),
                    alignment=(
                        AlignmentDraft((1, 0, 0), (1, 0)),
                        AlignmentDraft((0,), (1,)),
                        AlignmentDraft((8,), (0,)),
                    ),
                    detected_source_language="EN",
                ),
            )
        ]
    )

    result = await TranslateSubtitles(provider).execute(
        SubtitleTranslationRequest((("I", "know"),), "auto", "ru")
    )

    assert result.lines[0].translation_tokens == ("Я", "знаю")
    assert result.lines[0].alignment[0].source_indices == (0, 1)
    assert len(result.lines[0].alignment) == 1
    assert result.lines[0].detected_source_language == "en"


async def test_batch_retries_only_missing_lines():
    provider = Provider(
        [
            (
                SubtitleLineDraft(0, ("Первая",)),
            ),
            (
                SubtitleLineDraft(0, ("Вторая",)),
            ),
        ]
    )

    result = await TranslateSubtitles(provider).execute(
        SubtitleTranslationRequest((("First",), ("Second",)), "auto", "ru")
    )

    assert [line.translation_tokens[0] for line in result.lines] == [
        "Первая",
        "Вторая",
    ]
    assert provider.requests[1].lines == (("Second",),)


async def test_failed_batch_falls_back_to_individual_lines():
    provider = Provider(
        [
            RuntimeError("batch unavailable"),
            (SubtitleLineDraft(0, ("Один",)),),
            (SubtitleLineDraft(0, ("Два",)),),
        ]
    )

    result = await TranslateSubtitles(provider).execute(
        SubtitleTranslationRequest((("One",), ("Two",)), "auto", "ru")
    )

    assert [line.translation_tokens[0] for line in result.lines] == ["Один", "Два"]


async def test_rejects_invalid_request_before_provider_call():
    provider = Provider([])

    with pytest.raises(ValueError):
        await TranslateSubtitles(provider).execute(
            SubtitleTranslationRequest(((),), "auto", "ru")
        )

    assert provider.requests == []
