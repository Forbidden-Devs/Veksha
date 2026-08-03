"""Domain use case for extracting useful vocabulary from translated phrases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PhraseMiningRequest:
    source_text: str
    translated_text: str
    learning_language: str
    native_language: str
    proficiency: str
    existing_terms: tuple[str, ...] = ()
    maximum_candidates: int = 4


@dataclass(frozen=True, slots=True)
class VocabularyCandidateDraft:
    term: str
    translation: str
    transcription: str = ""
    context: str = ""


@dataclass(frozen=True, slots=True)
class VocabularyCandidate:
    term: str
    translation: str
    transcription: str
    context: str


class PhraseMiningProvider(Protocol):
    async def extract_vocabulary(
        self, request: PhraseMiningRequest
    ) -> tuple[VocabularyCandidateDraft, ...]: ...


class MinePhraseVocabulary:
    def __init__(self, provider: PhraseMiningProvider) -> None:
        self._provider = provider

    async def execute(
        self, request: PhraseMiningRequest
    ) -> tuple[VocabularyCandidate, ...]:
        normalized = _normalize_request(request)
        if len(normalized.source_text.split()) < 2:
            return ()
        drafts = await self._provider.extract_vocabulary(normalized)
        known = {term.casefold() for term in normalized.existing_terms}
        accepted: list[VocabularyCandidate] = []

        for draft in drafts:
            term = " ".join(draft.term.split())
            translation = " ".join(draft.translation.split())
            key = term.casefold()
            if not term or len(term) > 120 or not translation or key in known:
                continue
            known.add(key)
            context = " ".join(draft.context.split())
            if not context or context.casefold() not in normalized.source_text.casefold():
                context = normalized.source_text[:500]
            accepted.append(
                VocabularyCandidate(
                    term=term,
                    translation=translation,
                    transcription=draft.transcription.strip(),
                    context=context,
                )
            )
            if len(accepted) == normalized.maximum_candidates:
                break
        return tuple(accepted)


def _normalize_request(request: PhraseMiningRequest) -> PhraseMiningRequest:
    source_text = " ".join(request.source_text.split())
    translated_text = " ".join(request.translated_text.split())
    if not source_text or not translated_text:
        raise ValueError("phrase mining requires source text and translation")

    learning_language = request.learning_language.strip()
    native_language = request.native_language.strip()
    if not learning_language or not native_language:
        raise ValueError("phrase mining language pair must be complete")
    if not 1 <= request.maximum_candidates <= 8:
        raise ValueError("maximum candidates must be between one and eight")

    existing: list[str] = []
    seen: set[str] = set()
    for raw in request.existing_terms:
        term = " ".join(raw.split())
        key = term.casefold()
        if term and key not in seen:
            seen.add(key)
            existing.append(term)

    return PhraseMiningRequest(
        source_text=source_text[:4000],
        translated_text=translated_text[:4000],
        learning_language=learning_language,
        native_language=native_language,
        proficiency=request.proficiency.strip() or "intermediate",
        existing_terms=tuple(existing),
        maximum_candidates=request.maximum_candidates,
    )
