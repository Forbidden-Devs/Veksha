from __future__ import annotations

import pytest

from learning_core_v2.immersion import (
    BlockAnalysisRequest,
    ImmersionContext,
    SentenceDraft,
)
from learning_core_v2_adapters.immersion import CachedImmersionProvider


class Provider:
    def __init__(self):
        self.calls = 0

    async def analyze_block(self, request):
        self.calls += 1
        return [SentenceDraft(request.text, "B1", "translation")]


@pytest.mark.asyncio
async def test_cache_reuses_results_for_the_same_text_and_profile():
    provider = Provider()
    now = [10.0]
    cached = CachedImmersionProvider(provider, clock=lambda: now[0])
    request = BlockAnalysisRequest(
        "A sentence.", ImmersionContext("en", "ru", "B1")
    )

    first = await cached.analyze_block(request)
    second = await cached.analyze_block(request)

    assert first == second
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_cache_expires_and_evicts_the_least_recent_entry():
    provider = Provider()
    now = [10.0]
    cached = CachedImmersionProvider(
        provider, maximum_entries=1, ttl_seconds=5, clock=lambda: now[0]
    )
    context = ImmersionContext("en", "ru", "B1")
    first = BlockAnalysisRequest("First.", context)
    second = BlockAnalysisRequest("Second.", context)

    await cached.analyze_block(first)
    await cached.analyze_block(second)
    await cached.analyze_block(first)
    now[0] = 20.0
    await cached.analyze_block(first)

    assert provider.calls == 4
