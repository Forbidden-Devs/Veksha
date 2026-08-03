"""Bounded process-local cache for subtitle translations."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from learning_core_v2.subtitles import (
    SubtitleBatchTranslation,
    SubtitleLineTranslation,
    SubtitleTranslationRequest,
    TranslateSubtitles,
)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    value: SubtitleLineTranslation


class CachedSubtitleTranslator:
    def __init__(
        self,
        translator: TranslateSubtitles,
        *,
        max_entries: int = 2048,
        ttl_seconds: float = 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("subtitle cache bounds must be positive")
        self._translator = translator
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[
            tuple[str, str, tuple[str, ...]], _CacheEntry
        ] = OrderedDict()

    async def execute(
        self, request: SubtitleTranslationRequest
    ) -> SubtitleBatchTranslation:
        now = self._clock()
        results: list[SubtitleLineTranslation | None] = [None] * len(request.lines)
        missing_indices: list[int] = []
        for index, line in enumerate(request.lines):
            key = self._key(request, line)
            entry = self._entries.get(key)
            if entry is None or entry.expires_at <= now:
                self._entries.pop(key, None)
                missing_indices.append(index)
                continue
            self._entries.move_to_end(key)
            results[index] = entry.value

        if missing_indices:
            missing_request = SubtitleTranslationRequest(
                tuple(request.lines[index] for index in missing_indices),
                request.source_language,
                request.target_language,
            )
            translated = await self._translator.execute(missing_request)
            for index, value in zip(missing_indices, translated.lines, strict=True):
                results[index] = value
                key = self._key(request, request.lines[index])
                self._entries[key] = _CacheEntry(now + self._ttl_seconds, value)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)

        if any(result is None for result in results):
            raise ValueError("subtitle translation is incomplete")
        return SubtitleBatchTranslation(tuple(result for result in results if result))

    @staticmethod
    def _key(
        request: SubtitleTranslationRequest, line: tuple[str, ...]
    ) -> tuple[str, str, tuple[str, ...]]:
        return (
            request.source_language.strip().lower().replace("_", "-") or "auto",
            request.target_language.strip().lower().replace("_", "-"),
            tuple(token.strip() for token in line),
        )
