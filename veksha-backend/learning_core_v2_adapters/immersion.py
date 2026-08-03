"""Infrastructure helpers for the rewritten immersion use case."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Sequence

from learning_core_v2.immersion import BlockAnalysisRequest, SentenceDraft


CacheKey = tuple[str, str, str, str]


class CachedImmersionProvider:
    """Bounded process-local cache around an immersion content provider."""

    def __init__(
        self,
        provider,
        *,
        maximum_entries: int = 2048,
        ttl_seconds: float = 6 * 60 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if maximum_entries < 1:
            raise ValueError("maximum cache entries must be positive")
        if ttl_seconds <= 0:
            raise ValueError("cache lifetime must be positive")
        self._provider = provider
        self._maximum_entries = maximum_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[
            CacheKey, tuple[float, tuple[SentenceDraft, ...]]
        ] = OrderedDict()

    async def analyze_block(
        self, request: BlockAnalysisRequest
    ) -> Sequence[SentenceDraft]:
        key = (
            request.text,
            request.context.native_language,
            request.context.learning_language,
            request.context.learner_cefr,
        )
        now = self._clock()
        cached = self._entries.get(key)
        if cached is not None:
            expires_at, value = cached
            if expires_at > now:
                self._entries.move_to_end(key)
                return value
            self._entries.pop(key, None)

        value = tuple(await self._provider.analyze_block(request))
        self._entries[key] = (now + self._ttl_seconds, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._maximum_entries:
            self._entries.popitem(last=False)
        return value
