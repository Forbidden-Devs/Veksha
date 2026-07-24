"""Domain rules for embedding comprehensible input into page text."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, Sequence


CEFR_BANDS = ("A1", "A2", "B1", "B2", "C1", "C2")


@dataclass(frozen=True, slots=True)
class ImmersionContext:
    native_language: str
    learning_language: str
    learner_cefr: str


@dataclass(frozen=True, slots=True)
class SentenceDraft:
    text: str
    cefr: str
    translation: str = ""


@dataclass(frozen=True, slots=True)
class ImmersionSentence:
    text: str
    cefr: str
    translation: str


@dataclass(frozen=True, slots=True)
class ImmersionBlock:
    sentences: tuple[ImmersionSentence, ...] = ()


@dataclass(frozen=True, slots=True)
class BlockAnalysisRequest:
    text: str
    context: ImmersionContext


class ImmersionContentProvider(Protocol):
    async def analyze_block(
        self, request: BlockAnalysisRequest
    ) -> Sequence[SentenceDraft]: ...


class AnalyzeImmersion:
    def __init__(
        self,
        provider: ImmersionContentProvider,
        *,
        minimum_block_characters: int = 30,
        maximum_blocks: int = 60,
        concurrency: int = 6,
    ) -> None:
        if minimum_block_characters < 1:
            raise ValueError("minimum block size must be positive")
        if maximum_blocks < 1:
            raise ValueError("maximum blocks must be positive")
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self._provider = provider
        self._minimum_block_characters = minimum_block_characters
        self._maximum_blocks = maximum_blocks
        self._concurrency = concurrency

    async def execute(
        self, blocks: Sequence[str], context: ImmersionContext
    ) -> tuple[ImmersionBlock, ...]:
        selected = tuple(str(block or "").strip() for block in blocks[: self._maximum_blocks])
        if _language_base(context.native_language) == _language_base(
            context.learning_language
        ):
            return tuple(ImmersionBlock() for _ in selected)

        semaphore = asyncio.Semaphore(self._concurrency)

        async def analyze(text: str) -> ImmersionBlock:
            if len(text) < self._minimum_block_characters:
                return ImmersionBlock()
            try:
                async with semaphore:
                    drafts = await self._provider.analyze_block(
                        BlockAnalysisRequest(text, context)
                    )
            except Exception:
                return ImmersionBlock()
            return ImmersionBlock(_validate_sentences(text, drafts, context.learner_cefr))

        return tuple(await asyncio.gather(*(analyze(text) for text in selected)))


def _validate_sentences(
    source: str, drafts: Sequence[SentenceDraft], learner_cefr: str
) -> tuple[ImmersionSentence, ...]:
    cursor = 0
    accepted: list[ImmersionSentence] = []
    eligible = _translation_bands(learner_cefr)
    for draft in drafts:
        text = draft.text.strip()
        if not text:
            continue
        position = source.find(text, cursor)
        if position < 0:
            continue
        cursor = position + len(text)
        cefr = draft.cefr.strip().upper()
        if cefr not in CEFR_BANDS:
            cefr = ""
        translation = draft.translation.strip()
        if (
            cefr not in eligible
            or translation.casefold() == text.casefold()
        ):
            translation = ""
        accepted.append(ImmersionSentence(text, cefr, translation))
    return tuple(accepted)


def _translation_bands(learner_cefr: str) -> set[str]:
    normalized = learner_cefr.strip().upper()
    try:
        index = CEFR_BANDS.index(normalized)
    except ValueError:
        index = CEFR_BANDS.index("B1")
    return set(CEFR_BANDS[index : index + 2])


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]
