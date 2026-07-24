from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from learning_core_v2.translation import (
    TextTranslation,
    TranslateText,
    TranslationRequest,
    VocabularyObservation,
)


@dataclass
class StubProvider:
    response: TextTranslation
    requests: list[TranslationRequest] = field(default_factory=list)

    async def translate(self, request: TranslationRequest) -> TextTranslation:
        self.requests.append(request)
        return self.response


@dataclass
class RecordingVocabulary:
    observations: list[VocabularyObservation] = field(default_factory=list)

    async def observe(self, observation: VocabularyObservation) -> None:
        self.observations.append(observation)


@pytest.mark.asyncio
async def test_rejects_blank_text_without_calling_dependencies():
    provider = StubProvider(TextTranslation(text="unused"))
    vocabulary = RecordingVocabulary()

    with pytest.raises(ValueError, match="text must not be empty"):
        await TranslateText(provider, vocabulary).execute(
            TranslationRequest("  ", "auto", "ru", "intermediate")
        )

    assert provider.requests == []
    assert vocabulary.observations == []


@pytest.mark.asyncio
async def test_records_a_normalized_lexical_lookup():
    provider = StubProvider(
        TextTranslation(
            text="бежать",
            detected_language="en",
            is_lexical_unit=True,
            dictionary_form="run",
            transcription="rʌn",
        )
    )
    vocabulary = RecordingVocabulary()

    result = await TranslateText(provider, vocabulary).execute(
        TranslationRequest("  Running  ", "auto", "ru", "intermediate")
    )

    assert result.translation == "бежать"
    assert result.dictionary_form == "run"
    assert provider.requests[0].text == "Running"
    assert vocabulary.observations == [
        VocabularyObservation(
            source_text="Running",
            translation="бежать",
            source_language="en",
            is_lexical_unit=True,
            dictionary_form="run",
            transcription="rʌn",
        )
    ]


@pytest.mark.asyncio
async def test_uses_source_text_when_provider_omits_dictionary_form():
    provider = StubProvider(TextTranslation(text="слово", is_lexical_unit=True))
    vocabulary = RecordingVocabulary()

    result = await TranslateText(provider, vocabulary).execute(
        TranslationRequest("Word", "en", "ru", "beginner")
    )

    assert result.dictionary_form == "word"
    assert vocabulary.observations[0].dictionary_form == "word"


@pytest.mark.asyncio
async def test_empty_translation_does_not_change_vocabulary():
    provider = StubProvider(TextTranslation(text="  ", is_lexical_unit=False))
    vocabulary = RecordingVocabulary()

    result = await TranslateText(provider, vocabulary).execute(
        TranslationRequest("A short phrase", "en", "ru", "advanced")
    )

    assert result.translation == ""
    assert vocabulary.observations == []
