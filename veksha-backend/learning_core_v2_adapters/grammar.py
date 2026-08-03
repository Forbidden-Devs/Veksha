"""Bounded in-process cache for Grammar Memory analysis drafts."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable

from learning_core_v2.grammar_analysis import (
    GrammarAnalysisDraft,
    GrammarAnalysisProvider,
    GrammarAnalysisRequest,
)


class CachedGrammarProvider:
    def __init__(
        self,
        provider: GrammarAnalysisProvider,
        *,
        maximum_entries: int = 256,
        ttl_seconds: float = 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if maximum_entries < 1 or ttl_seconds <= 0:
            raise ValueError("grammar cache limits must be positive")
        self._provider = provider
        self._maximum_entries = maximum_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[
            GrammarAnalysisRequest, tuple[float, GrammarAnalysisDraft]
        ] = OrderedDict()

    async def analyze_grammar(
        self, request: GrammarAnalysisRequest
    ) -> GrammarAnalysisDraft:
        now = self._clock()
        cached = self._entries.pop(request, None)
        if cached is not None and now - cached[0] < self._ttl_seconds:
            self._entries[request] = cached
            return cached[1]
        draft = await self._provider.analyze_grammar(request)
        self._entries[request] = (now, draft)
        while len(self._entries) > self._maximum_entries:
            self._entries.popitem(last=False)
        return draft
