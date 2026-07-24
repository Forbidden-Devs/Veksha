"""Translation use case expressed without transport or provider dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    text: str
    source_language: str
    target_language: str
    proficiency: str
    bidirectional: bool = False


@dataclass(frozen=True, slots=True)
class TextTranslation:
    text: str
    detected_language: str | None = None
    is_lexical_unit: bool = False
    dictionary_form: str = ""
    transcription: str = ""


@dataclass(frozen=True, slots=True)
class TranslationResult:
    translation: str
    detected_source_language: str | None
    is_lexical_unit: bool
    dictionary_form: str
    transcription: str


@dataclass(frozen=True, slots=True)
class VocabularyObservation:
    source_text: str
    translation: str
    source_language: str
    is_lexical_unit: bool
    dictionary_form: str
    transcription: str


class TranslationProvider(Protocol):
    async def translate(self, request: TranslationRequest) -> TextTranslation:
        """Translate and classify text without changing user state."""


class VocabularySink(Protocol):
    async def observe(self, observation: VocabularyObservation) -> None:
        """Record a successful lookup according to vocabulary policy."""


class TranslateText:
    def __init__(
        self,
        provider: TranslationProvider,
        vocabulary: VocabularySink,
    ) -> None:
        self._provider = provider
        self._vocabulary = vocabulary

    async def execute(self, request: TranslationRequest) -> TranslationResult:
        source_text = request.text.strip()
        if not source_text:
            raise ValueError("text must not be empty")
        if not request.target_language.strip():
            raise ValueError("target language must not be empty")

        normalized_request = TranslationRequest(
            text=source_text,
            source_language=request.source_language.strip() or "auto",
            target_language=request.target_language.strip(),
            proficiency=request.proficiency.strip(),
            bidirectional=request.bidirectional,
        )
        translated = await self._provider.translate(normalized_request)
        translated_text = translated.text.strip()
        dictionary_form = translated.dictionary_form.strip()

        if translated.is_lexical_unit and not dictionary_form:
            dictionary_form = source_text.casefold()

        result = TranslationResult(
            translation=translated_text,
            detected_source_language=translated.detected_language,
            is_lexical_unit=translated.is_lexical_unit,
            dictionary_form=dictionary_form,
            transcription=translated.transcription.strip(),
        )

        if translated_text:
            await self._vocabulary.observe(
                VocabularyObservation(
                    source_text=source_text,
                    translation=translated_text,
                    source_language=(
                        translated.detected_language
                        or normalized_request.source_language
                    ),
                    is_lexical_unit=translated.is_lexical_unit,
                    dictionary_form=dictionary_form,
                    transcription=result.transcription,
                )
            )

        return result
