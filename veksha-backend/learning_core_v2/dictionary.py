"""Domain use case for enriching a tracked dictionary entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DictionaryLookupRequest:
    term: str
    learning_language: str
    native_language: str
    proficiency: str
    context: str = ""


@dataclass(frozen=True, slots=True)
class DictionaryDraft:
    headword: str
    translation: str
    transcription: str = ""


@dataclass(frozen=True, slots=True)
class DictionaryDetails:
    headword: str
    translation: str
    transcription: str


class DictionaryContentProvider(Protocol):
    async def lookup_dictionary_entry(
        self, request: DictionaryLookupRequest
    ) -> DictionaryDraft: ...


class EnrichDictionaryEntry:
    def __init__(self, provider: DictionaryContentProvider) -> None:
        self._provider = provider

    async def execute(self, request: DictionaryLookupRequest) -> DictionaryDetails:
        term = " ".join(request.term.split())
        if not term:
            raise ValueError("dictionary term must not be empty")
        if len(term) > 200:
            raise ValueError("dictionary term is too long")

        learning_language = request.learning_language.strip()
        native_language = request.native_language.strip()
        if not learning_language or not native_language:
            raise ValueError("dictionary language pair must be complete")

        normalized = DictionaryLookupRequest(
            term=term,
            learning_language=learning_language,
            native_language=native_language,
            proficiency=request.proficiency.strip() or "intermediate",
            context=request.context.strip(),
        )
        draft = await self._provider.lookup_dictionary_entry(normalized)
        headword = " ".join(draft.headword.split()) or term
        translation = draft.translation.strip()
        transcription = draft.transcription.strip()
        if not translation:
            raise ValueError("dictionary provider returned an empty translation")
        return DictionaryDetails(headword, translation, transcription)
