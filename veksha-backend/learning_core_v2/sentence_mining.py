"""Domain rules for building level-aware sentence-mining cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


CEFR_BANDS = {"A1", "A2", "B1", "B2", "C1", "C2"}


@dataclass(frozen=True, slots=True)
class SentenceMiningRequest:
    term: str
    known_translation: str
    context: str
    learning_language: str
    native_language: str
    learner_cefr: str
    stretch_cefr: str
    learner_example_count: int
    stretch_example_count: int


@dataclass(frozen=True, slots=True)
class ExampleDraft:
    sentence: str
    translation: str
    cefr: str


@dataclass(frozen=True, slots=True)
class CollocationDraft:
    text: str
    translation: str = ""


@dataclass(frozen=True, slots=True)
class SentenceMiningDraft:
    examples: tuple[ExampleDraft, ...]
    mnemonic: str
    collocations: tuple[CollocationDraft, ...]


@dataclass(frozen=True, slots=True)
class MiningExample:
    sentence: str
    translation: str
    level: str
    is_higher: bool


@dataclass(frozen=True, slots=True)
class MiningCollocation:
    text: str
    translation: str


@dataclass(frozen=True, slots=True)
class SentenceMiningCard:
    examples: tuple[MiningExample, ...]
    mnemonic: str
    collocations: tuple[MiningCollocation, ...]


class SentenceMiningProvider(Protocol):
    async def build_sentence_mining_card(
        self, request: SentenceMiningRequest
    ) -> SentenceMiningDraft: ...


class BuildSentenceMiningCard:
    def __init__(self, provider: SentenceMiningProvider) -> None:
        self._provider = provider

    async def execute(self, request: SentenceMiningRequest) -> SentenceMiningCard:
        normalized = _normalize_request(request)
        draft = await self._provider.build_sentence_mining_card(normalized)
        examples = _select_examples(draft.examples, normalized)
        expected = normalized.learner_example_count + normalized.stretch_example_count
        if len(examples) != expected:
            raise ValueError("sentence mining provider returned incomplete examples")

        mnemonic = draft.mnemonic.strip()[:500]
        if not mnemonic:
            raise ValueError("sentence mining provider returned an empty mnemonic")

        collocations = _select_collocations(draft.collocations)
        if len(collocations) < 3:
            raise ValueError("sentence mining provider returned too few collocations")
        return SentenceMiningCard(tuple(examples), mnemonic, tuple(collocations))


def _normalize_request(request: SentenceMiningRequest) -> SentenceMiningRequest:
    term = " ".join(request.term.split())
    if not term:
        raise ValueError("sentence mining term must not be empty")
    if len(term) > 200:
        raise ValueError("sentence mining term is too long")

    learning_language = request.learning_language.strip()
    native_language = request.native_language.strip()
    if not learning_language or not native_language:
        raise ValueError("sentence mining language pair must be complete")

    learner_cefr = request.learner_cefr.strip().upper()
    stretch_cefr = request.stretch_cefr.strip().upper()
    if learner_cefr not in CEFR_BANDS or stretch_cefr not in CEFR_BANDS:
        raise ValueError("sentence mining CEFR band is invalid")
    if not 1 <= request.learner_example_count <= 5:
        raise ValueError("learner example count must be between one and five")
    if not 0 <= request.stretch_example_count <= 3:
        raise ValueError("stretch example count must be between zero and three")

    return SentenceMiningRequest(
        term=term,
        known_translation=request.known_translation.strip(),
        context=request.context.strip(),
        learning_language=learning_language,
        native_language=native_language,
        learner_cefr=learner_cefr,
        stretch_cefr=stretch_cefr,
        learner_example_count=request.learner_example_count,
        stretch_example_count=request.stretch_example_count,
    )


def _select_examples(
    drafts: tuple[ExampleDraft, ...], request: SentenceMiningRequest
) -> list[MiningExample]:
    same_band = request.learner_cefr == request.stretch_cefr
    learner_limit = request.learner_example_count + (
        request.stretch_example_count if same_band else 0
    )
    learner: list[MiningExample] = []
    stretch: list[MiningExample] = []
    seen: set[str] = set()

    for draft in drafts:
        sentence = " ".join(draft.sentence.split())
        translation = " ".join(draft.translation.split())
        cefr = draft.cefr.strip().upper()
        key = sentence.casefold()
        if not sentence or not translation or key in seen:
            continue
        seen.add(key)
        if cefr == request.learner_cefr and len(learner) < learner_limit:
            learner.append(MiningExample(sentence, translation, cefr, False))
        elif (
            not same_band
            and cefr == request.stretch_cefr
            and len(stretch) < request.stretch_example_count
        ):
            stretch.append(MiningExample(sentence, translation, cefr, True))

    return [*learner, *stretch]


def _select_collocations(
    drafts: tuple[CollocationDraft, ...],
) -> list[MiningCollocation]:
    result: list[MiningCollocation] = []
    seen: set[str] = set()
    for draft in drafts:
        text = " ".join(draft.text.split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(
            MiningCollocation(text, " ".join(draft.translation.split()))
        )
        if len(result) == 5:
            break
    return result
