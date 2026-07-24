from __future__ import annotations

import pytest

from learning_core_v2.immersion import (
    AnalyzeImmersion,
    ImmersionContext,
    SentenceDraft,
)


class StubProvider:
    def __init__(self, results=None, failing_text="") -> None:
        self.results = results or {}
        self.failing_text = failing_text
        self.requests = []

    async def analyze_block(self, request):
        self.requests.append(request)
        if request.text == self.failing_text:
            raise RuntimeError("provider unavailable")
        return self.results.get(request.text, ())


@pytest.mark.asyncio
async def test_skips_short_blocks_and_equal_language_pairs_without_provider_calls():
    provider = StubProvider()
    use_case = AnalyzeImmersion(provider, minimum_block_characters=10)

    short = await use_case.execute(
        ["tiny"], ImmersionContext("ru", "en", "B1")
    )
    same_language = await use_case.execute(
        ["Long enough source text."], ImmersionContext("en-US", "en", "B1")
    )

    assert short[0].sentences == ()
    assert same_language[0].sentences == ()
    assert provider.requests == []


@pytest.mark.asyncio
async def test_preserves_block_order_and_isolates_provider_failures():
    first = "First sentence is long enough."
    broken = "This block triggers a provider failure."
    provider = StubProvider(
        {first: [SentenceDraft(first, "B1", "Первое предложение.")]},
        failing_text=broken,
    )

    result = await AnalyzeImmersion(provider, minimum_block_characters=5).execute(
        [first, broken], ImmersionContext("en", "ru", "B1")
    )

    assert result[0].sentences[0].translation == "Первое предложение."
    assert result[1].sentences == ()


@pytest.mark.asyncio
async def test_caps_the_number_of_blocks_before_calling_provider():
    first = "First block is long enough."
    second = "Second block is also long enough."
    provider = StubProvider()

    result = await AnalyzeImmersion(
        provider, minimum_block_characters=5, maximum_blocks=1
    ).execute([first, second], ImmersionContext("en", "ru", "B1"))

    assert len(result) == 1
    assert [request.text for request in provider.requests] == [first]


@pytest.mark.asyncio
async def test_rejects_hallucinated_and_out_of_order_sentences():
    source = "One sentence. Two sentence. Three sentence."
    provider = StubProvider(
        {
            source: [
                SentenceDraft("Two sentence.", "B2", "Два."),
                SentenceDraft("Made up sentence.", "B1", "Выдумано."),
                SentenceDraft("One sentence.", "B1", "Один."),
                SentenceDraft("Three sentence.", "C1", "Три."),
            ]
        }
    )

    result = await AnalyzeImmersion(provider, minimum_block_characters=5).execute(
        [source], ImmersionContext("en", "ru", "B1")
    )

    assert [item.text for item in result[0].sentences] == [
        "Two sentence.",
        "Three sentence.",
    ]
    assert result[0].sentences[0].translation == "Два."
    assert result[0].sentences[1].translation == ""


@pytest.mark.asyncio
async def test_clears_echo_translations_and_invalid_cefr_values():
    source = "A useful sentence. Another useful sentence."
    provider = StubProvider(
        {
            source: [
                SentenceDraft("A useful sentence.", "B1", "A useful sentence."),
                SentenceDraft("Another useful sentence.", "unknown", "Перевод."),
            ]
        }
    )

    result = await AnalyzeImmersion(provider, minimum_block_characters=5).execute(
        [source], ImmersionContext("en", "ru", "B1")
    )

    assert result[0].sentences[0].translation == ""
    assert result[0].sentences[1].cefr == ""
    assert result[0].sentences[1].translation == ""
