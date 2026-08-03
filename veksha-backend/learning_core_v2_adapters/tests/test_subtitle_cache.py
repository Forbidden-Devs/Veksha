import pytest

from learning_core_v2.subtitles import (
    SubtitleBatchTranslation,
    SubtitleLineTranslation,
    SubtitleTranslationRequest,
)
from learning_core_v2_adapters.subtitles import CachedSubtitleTranslator


pytestmark = pytest.mark.asyncio


class Translator:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return SubtitleBatchTranslation(
            tuple(
                SubtitleLineTranslation((f"translated:{line[0]}",))
                for line in request.lines
            )
        )


async def test_cache_reuses_lines_and_only_requests_misses():
    translator = Translator()
    cached = CachedSubtitleTranslator(translator)

    first = SubtitleTranslationRequest((("One",), ("Two",)), "auto", "ru")
    await cached.execute(first)
    result = await cached.execute(
        SubtitleTranslationRequest((("Two",), ("Three",)), "auto", "ru")
    )

    assert len(translator.requests) == 2
    assert translator.requests[1].lines == (("Three",),)
    assert [line.translation_tokens[0] for line in result.lines] == [
        "translated:Two",
        "translated:Three",
    ]


async def test_cache_expires_and_evicts_oldest_entry():
    now = [0.0]
    translator = Translator()
    cached = CachedSubtitleTranslator(
        translator, max_entries=1, ttl_seconds=5, clock=lambda: now[0]
    )

    await cached.execute(SubtitleTranslationRequest((("One",),), "auto", "ru"))
    await cached.execute(SubtitleTranslationRequest((("Two",),), "auto", "ru"))
    await cached.execute(SubtitleTranslationRequest((("One",),), "auto", "ru"))
    now[0] = 10
    await cached.execute(SubtitleTranslationRequest((("One",),), "auto", "ru"))

    assert len(translator.requests) == 4
