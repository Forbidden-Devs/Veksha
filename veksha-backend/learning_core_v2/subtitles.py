"""Validated dual-subtitle translation and token alignment."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SubtitleTranslationRequest:
    lines: tuple[tuple[str, ...], ...]
    source_language: str
    target_language: str


@dataclass(frozen=True, slots=True)
class AlignmentDraft:
    source_indices: tuple[int, ...]
    translation_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SubtitleLineDraft:
    index: int
    translation_tokens: tuple[str, ...]
    alignment: tuple[AlignmentDraft, ...] = ()
    detected_source_language: str | None = None


@dataclass(frozen=True, slots=True)
class Alignment:
    source_indices: tuple[int, ...]
    translation_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SubtitleLineTranslation:
    translation_tokens: tuple[str, ...]
    alignment: tuple[Alignment, ...] = ()
    detected_source_language: str | None = None


@dataclass(frozen=True, slots=True)
class SubtitleBatchTranslation:
    lines: tuple[SubtitleLineTranslation, ...]


class SubtitleTranslationProvider(Protocol):
    async def translate_subtitles(
        self, request: SubtitleTranslationRequest
    ) -> tuple[SubtitleLineDraft, ...]: ...


class TranslateSubtitles:
    """Translate adjacent cues, retrying only cues omitted by a batch response."""

    def __init__(self, provider: SubtitleTranslationProvider) -> None:
        self._provider = provider

    async def execute(
        self, request: SubtitleTranslationRequest
    ) -> SubtitleBatchTranslation:
        normalized = _normalize_request(request)
        accepted: dict[int, SubtitleLineTranslation] = {}
        try:
            drafts = await self._provider.translate_subtitles(normalized)
        except Exception:
            drafts = ()
        for draft in drafts:
            if draft.index in accepted or not 0 <= draft.index < len(normalized.lines):
                continue
            translation = _ground_line(draft, len(normalized.lines[draft.index]))
            if translation is not None:
                accepted[draft.index] = translation

        missing = [index for index in range(len(normalized.lines)) if index not in accepted]
        if missing:
            retries = await asyncio.gather(
                *(self._translate_one(normalized, index) for index in missing)
            )
            accepted.update(zip(missing, retries, strict=True))

        return SubtitleBatchTranslation(
            tuple(accepted[index] for index in range(len(normalized.lines)))
        )

    async def _translate_one(
        self, request: SubtitleTranslationRequest, index: int
    ) -> SubtitleLineTranslation:
        single = SubtitleTranslationRequest(
            lines=(request.lines[index],),
            source_language=request.source_language,
            target_language=request.target_language,
        )
        drafts = await self._provider.translate_subtitles(single)
        for draft in drafts:
            if draft.index != 0:
                continue
            translation = _ground_line(draft, len(single.lines[0]))
            if translation is not None:
                return translation
        raise ValueError("subtitle provider returned no usable translation")


def _normalize_request(request: SubtitleTranslationRequest) -> SubtitleTranslationRequest:
    if not 1 <= len(request.lines) <= 12:
        raise ValueError("subtitle request must contain between 1 and 12 lines")
    lines: list[tuple[str, ...]] = []
    for line in request.lines:
        tokens = tuple(token.strip() for token in line if token.strip())
        if not 1 <= len(tokens) <= 40:
            raise ValueError("each subtitle line must contain between 1 and 40 tokens")
        if any(len(token) > 48 for token in tokens):
            raise ValueError("subtitle token is too long")
        lines.append(tokens)
    source = request.source_language.strip().lower().replace("_", "-") or "auto"
    target = request.target_language.strip().lower().replace("_", "-")
    if not 2 <= len(target) <= 8:
        raise ValueError("subtitle target language is invalid")
    return SubtitleTranslationRequest(tuple(lines), source, target)


def _ground_line(
    draft: SubtitleLineDraft, source_count: int
) -> SubtitleLineTranslation | None:
    tokens = tuple(str(token).strip() for token in draft.translation_tokens if str(token).strip())[:60]
    if not tokens:
        return None
    seen_source: set[int] = set()
    seen_translation: set[int] = set()
    alignment: list[Alignment] = []
    for group in draft.alignment:
        source = tuple(sorted(set(group.source_indices)))
        translated = tuple(sorted(set(group.translation_indices)))
        if not source or not translated:
            continue
        if any(index < 0 or index >= source_count for index in source):
            continue
        if any(index < 0 or index >= len(tokens) for index in translated):
            continue
        if seen_source.intersection(source) or seen_translation.intersection(translated):
            continue
        seen_source.update(source)
        seen_translation.update(translated)
        alignment.append(Alignment(source, translated))
    language = (draft.detected_source_language or "").strip().lower()[:8] or None
    return SubtitleLineTranslation(tokens, tuple(alignment), language)
