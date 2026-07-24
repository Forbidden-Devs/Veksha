from __future__ import annotations

import pytest

from learning_core_v2.dictionary import (
    DictionaryDraft,
    DictionaryLookupRequest,
    EnrichDictionaryEntry,
)


class StubProvider:
    def __init__(self, draft: DictionaryDraft) -> None:
        self.draft = draft
        self.requests = []

    async def lookup_dictionary_entry(self, request):
        self.requests.append(request)
        return self.draft


@pytest.mark.asyncio
async def test_enrichment_normalizes_input_and_provider_output():
    provider = StubProvider(
        DictionaryDraft(" serendipity ", " счастливая случайность ", " /ˌserənˈdɪpəti/ ")
    )

    result = await EnrichDictionaryEntry(provider).execute(
        DictionaryLookupRequest("  serendipity  ", " en ", " ru ", " a2 ")
    )

    assert result.headword == "serendipity"
    assert result.translation == "счастливая случайность"
    assert result.transcription == "/ˌserənˈdɪpəti/"
    assert provider.requests[0] == DictionaryLookupRequest(
        "serendipity", "en", "ru", "a2"
    )


@pytest.mark.asyncio
async def test_missing_headword_falls_back_to_requested_term():
    provider = StubProvider(DictionaryDraft("", "случайность"))

    result = await EnrichDictionaryEntry(provider).execute(
        DictionaryLookupRequest("serendipity", "en", "ru", "a2")
    )

    assert result.headword == "serendipity"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup_request",
    [
        DictionaryLookupRequest(" ", "en", "ru", "a2"),
        DictionaryLookupRequest("word", "", "ru", "a2"),
        DictionaryLookupRequest("word", "en", "", "a2"),
    ],
)
async def test_invalid_requests_are_rejected_before_provider(lookup_request):
    provider = StubProvider(DictionaryDraft("word", "слово"))

    with pytest.raises(ValueError):
        await EnrichDictionaryEntry(provider).execute(lookup_request)

    assert provider.requests == []


@pytest.mark.asyncio
async def test_empty_translation_is_rejected():
    provider = StubProvider(DictionaryDraft("word", "   "))

    with pytest.raises(ValueError, match="empty translation"):
        await EnrichDictionaryEntry(provider).execute(
            DictionaryLookupRequest("word", "en", "ru", "a2")
        )
