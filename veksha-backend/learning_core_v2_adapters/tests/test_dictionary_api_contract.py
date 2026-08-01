from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

from api import settings
from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.dictionary import DictionaryDetails
from learning_core_v2_adapters.openai_responses import LanguageProviderError


@dataclass
class FakeSettings:
    target_lang: str = "en"
    native_lang: str = "ru"
    english_level: str = "a2"


@dataclass
class FakeStorage:
    settings: FakeSettings = field(default_factory=FakeSettings)
    lexical_items: list[LexicalItem] = field(default_factory=list)
    saves: int = 0

    def find_lexical_item_by_term(self, name):
        key = name.strip().casefold()
        return next(
            (item for item in self.lexical_items if item.term.casefold() == key), None
        )

    def save(self):
        self.saves += 1


class RecordingEnrichment:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return DictionaryDetails(
            "serendipity", "счастливая случайность", "/ˌserənˈdɪpəti/"
        )


@pytest.mark.asyncio
async def test_add_word_uses_v2_enrichment_and_keeps_public_response(monkeypatch):
    storage = FakeStorage()
    service = RecordingEnrichment()
    monkeypatch.setattr(settings, "get_storage", lambda _username: storage)
    monkeypatch.setattr(settings, "build_dictionary_enrichment", lambda: service)

    response = await settings.api_add_kb_word(
        settings.AddWordRequest(word="  Serendipity  "), "tester"
    )
    repeated = await settings.api_add_kb_word(
        settings.AddWordRequest(word="serendipity"), "tester"
    )

    assert service.requests[0].term == "serendipity"
    assert service.requests[0].learning_language == "en"
    assert service.requests[0].native_language == "ru"
    assert response.translation == "счастливая случайность"
    assert response.transcription == "/ˌserənˈdɪpəti/"
    assert repeated == response
    assert len(service.requests) == 1
    assert storage.saves == 1


class FailingEnrichment:
    async def execute(self, _request):
        raise LanguageProviderError("unavailable")


@pytest.mark.asyncio
async def test_new_word_is_rolled_back_when_v2_enrichment_fails(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(settings, "get_storage", lambda _username: storage)
    monkeypatch.setattr(
        settings, "build_dictionary_enrichment", lambda: FailingEnrichment()
    )

    with pytest.raises(HTTPException) as caught:
        await settings.api_add_kb_word(
            settings.AddWordRequest(word="serendipity"), "tester"
        )

    assert caught.value.status_code == 502
    assert storage.lexical_items == []
