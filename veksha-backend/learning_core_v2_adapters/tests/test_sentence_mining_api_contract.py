from __future__ import annotations

from dataclasses import dataclass

import pytest

from api import settings
from learning_core_v2.sentence_mining import (
    MiningCollocation,
    MiningExample,
    SentenceMiningCard,
)
from models import Word


@dataclass
class FakeSettings:
    english_level: str = "a2"
    target_lang: str = "en"
    native_lang: str = "ru"
    mining_same_level_examples: int = 1
    mining_higher_level_examples: int = 1


class FakeStorage:
    def __init__(self):
        self.settings = FakeSettings()
        self.word = Word(
            name="make",
            language="en",
            translation="делать",
            context="I make coffee.",
        )
        self.saves = 0

    def find_word(self, name):
        return self.word if name.casefold() == self.word.name.casefold() else None

    def save(self):
        self.saves += 1


class RecordingBuilder:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return SentenceMiningCard(
            examples=(
                MiningExample("I make coffee.", "Я готовлю кофе.", "A2", False),
                MiningExample(
                    "We made a decision.", "Мы приняли решение.", "B1", True
                ),
            ),
            mnemonic="Запомните make.",
            collocations=(
                MiningCollocation("make progress", "добиваться прогресса"),
                MiningCollocation("make sure", "убедиться"),
                MiningCollocation("make a choice", "сделать выбор"),
            ),
        )


@pytest.mark.asyncio
async def test_endpoint_uses_v2_card_and_reuses_matching_configuration(monkeypatch):
    storage = FakeStorage()
    builder = RecordingBuilder()
    monkeypatch.setattr(settings, "get_storage", lambda _username: storage)
    monkeypatch.setattr(settings, "_sentence_mining_v2_enabled", lambda: True)
    monkeypatch.setattr(settings, "build_sentence_mining", lambda: builder)

    async def forbidden_legacy_call(**_kwargs):
        raise AssertionError("legacy sentence mining was called")

    monkeypatch.setattr(settings.llm, "generate_sentence_mining", forbidden_legacy_call)

    first = await settings.api_mine_kb_word(
        settings.SentenceMiningRequest(word="make"), "tester"
    )
    second = await settings.api_mine_kb_word(
        settings.SentenceMiningRequest(word="make"), "tester"
    )

    assert builder.requests[0].learner_cefr == "A2"
    assert builder.requests[0].stretch_cefr == "B1"
    assert first.sentence_mining is not None
    assert first.sentence_mining.examples[1].is_higher is True
    assert second == first
    assert len(builder.requests) == 1
    assert storage.saves == 1


@pytest.mark.asyncio
async def test_force_regenerates_existing_v2_card(monkeypatch):
    storage = FakeStorage()
    builder = RecordingBuilder()
    monkeypatch.setattr(settings, "get_storage", lambda _username: storage)
    monkeypatch.setattr(settings, "_sentence_mining_v2_enabled", lambda: True)
    monkeypatch.setattr(settings, "build_sentence_mining", lambda: builder)

    await settings.api_mine_kb_word(
        settings.SentenceMiningRequest(word="make"), "tester"
    )
    await settings.api_mine_kb_word(
        settings.SentenceMiningRequest(word="make", force=True), "tester"
    )

    assert len(builder.requests) == 2
    assert storage.saves == 2
