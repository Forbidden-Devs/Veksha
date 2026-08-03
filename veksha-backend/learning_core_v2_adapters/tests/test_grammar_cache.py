import pytest

from learning_core_v2.grammar_analysis import (
    GrammarAnalysisDraft,
    GrammarAnalysisRequest,
)
from learning_core_v2_adapters.grammar import CachedGrammarProvider


class Provider:
    def __init__(self):
        self.calls = []

    async def analyze_grammar(self, request):
        self.calls.append(request)
        return GrammarAnalysisDraft()


@pytest.mark.asyncio
async def test_cache_reuses_the_same_text_and_profile():
    provider = Provider()
    cached = CachedGrammarProvider(provider)
    request = GrammarAnalysisRequest("She has arrived.", "ru", "b1")

    assert await cached.analyze_grammar(request) == await cached.analyze_grammar(request)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_cache_expires_and_evicts_oldest_entry():
    now = [0.0]
    provider = Provider()
    cached = CachedGrammarProvider(
        provider,
        maximum_entries=1,
        ttl_seconds=10,
        clock=lambda: now[0],
    )
    first = GrammarAnalysisRequest("She has arrived.", "ru", "b1")
    second = GrammarAnalysisRequest("They had left.", "ru", "b1")

    await cached.analyze_grammar(first)
    await cached.analyze_grammar(second)
    await cached.analyze_grammar(first)
    now[0] = 20
    await cached.analyze_grammar(first)

    assert len(provider.calls) == 4
