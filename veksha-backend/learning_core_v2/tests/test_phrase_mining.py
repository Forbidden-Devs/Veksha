from __future__ import annotations

import pytest

from learning_core_v2.phrase_mining import (
    MinePhraseVocabulary,
    PhraseMiningRequest,
    VocabularyCandidateDraft,
)


class StubProvider:
    def __init__(self, drafts=()) -> None:
        self.drafts = tuple(drafts)
        self.requests = []

    async def extract_vocabulary(self, request):
        self.requests.append(request)
        return self.drafts


REQUEST = PhraseMiningRequest(
    source_text="She came across an old photograph in the attic.",
    translated_text="Она случайно нашла старую фотографию на чердаке.",
    learning_language="en",
    native_language="ru",
    proficiency="b1",
    existing_terms=("attic",),
    maximum_candidates=2,
)


@pytest.mark.asyncio
async def test_extracts_new_candidates_with_dictionary_details():
    provider = StubProvider(
        (
            VocabularyCandidateDraft(
                "come across", "случайно найти", "/kʌm əˈkrɒs/", "came across"
            ),
            VocabularyCandidateDraft("attic", "чердак", "/ˈætɪk/", "the attic"),
            VocabularyCandidateDraft("photograph", "фотография", context="old photograph"),
        )
    )

    result = await MinePhraseVocabulary(provider).execute(REQUEST)

    assert [item.term for item in result] == ["come across", "photograph"]
    assert result[0].context == "came across"
    assert result[0].transcription == "/kʌm əˈkrɒs/"


@pytest.mark.asyncio
async def test_deduplicates_candidates_and_replaces_hallucinated_context():
    provider = StubProvider(
        (
            VocabularyCandidateDraft("Photograph", "фотография", context="not present"),
            VocabularyCandidateDraft("photograph", "дубликат"),
            VocabularyCandidateDraft("empty translation", ""),
        )
    )

    result = await MinePhraseVocabulary(provider).execute(REQUEST)

    assert len(result) == 1
    assert result[0].context == REQUEST.source_text


@pytest.mark.asyncio
async def test_candidate_limit_is_enforced_after_filtering():
    provider = StubProvider(
        tuple(
            VocabularyCandidateDraft(f"term {index}", f"перевод {index}")
            for index in range(5)
        )
    )

    result = await MinePhraseVocabulary(provider).execute(REQUEST)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_invalid_request_is_rejected_before_provider():
    provider = StubProvider()

    with pytest.raises(ValueError):
        await MinePhraseVocabulary(provider).execute(
            PhraseMiningRequest("", "translation", "en", "ru", "b1")
        )

    assert provider.requests == []


@pytest.mark.asyncio
async def test_single_token_does_not_start_phrase_mining():
    provider = StubProvider((VocabularyCandidateDraft("word", "слово"),))

    result = await MinePhraseVocabulary(provider).execute(
        PhraseMiningRequest("word", "слово", "en", "ru", "b1")
    )

    assert result == ()
    assert provider.requests == []
