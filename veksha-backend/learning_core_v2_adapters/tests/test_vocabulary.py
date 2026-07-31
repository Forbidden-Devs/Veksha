from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from learning_core_v2.phrase_mining import VocabularyCandidate
from learning_core_v2.translation import VocabularyObservation
from learning_core_v2_adapters.vocabulary import UserStorageVocabularyInboxSink


@dataclass
class FakeSettings:
    target_lang: str = "en"
    native_lang: str = "ru"
    english_level: str = "b1"


@dataclass
class FakeWord:
    name: str
    language: str = "en"
    translation: str = ""
    transcription: str = ""


@dataclass
class FakeStorage:
    settings: FakeSettings = field(default_factory=FakeSettings)
    words: dict[str, FakeWord] = field(default_factory=dict)
    patches: list = field(default_factory=list)
    saves: int = 0
    vocabulary_inbox: list = field(default_factory=list)

    def find_word(self, name):
        return self.words.get(name)

    def apply_kb_changes(self, patches):
        self.patches.extend(patches)
        for patch in patches:
            self.words[patch.value] = FakeWord(patch.value)

    def save(self):
        self.saves += 1


def observation(**overrides):
    values = {
        "source_text": "Running",
        "translation": "бежать",
        "source_language": "en",
        "is_lexical_unit": True,
        "dictionary_form": "run",
        "transcription": "rʌn",
    }
    values.update(overrides)
    return VocabularyObservation(**values)


class StubPhraseMiner:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return (
            VocabularyCandidate(
                "come across",
                "случайно найти",
                "/kʌm əˈkrɒs/",
                "came across",
            ),
        )


@pytest.mark.asyncio
async def test_inbox_sink_suggests_a_word_without_adding_it_to_training():
    storage = FakeStorage()
    sink = UserStorageVocabularyInboxSink(
        storage,
        clock=lambda: 42.0,
        identifier=lambda: "suggestion-1",
    )

    await sink.observe(
        observation(source_url="https://example.test/article")
    )

    assert storage.patches == []
    assert storage.vocabulary_inbox[0].term == "run"
    assert storage.vocabulary_inbox[0].encounters[0].source_url == (
        "https://example.test/article"
    )


@pytest.mark.asyncio
async def test_inbox_sink_keeps_phrase_candidates_out_of_training():
    storage = FakeStorage()
    sink = UserStorageVocabularyInboxSink(
        storage,
        phrase_miner=StubPhraseMiner(),
        clock=lambda: 42.0,
        identifier=lambda: "suggestion-1",
    )

    await sink.observe(
        observation(
            source_text="She came across an old photograph.",
            translation="Она случайно нашла старую фотографию.",
            is_lexical_unit=False,
            dictionary_form="",
        )
    )

    assert storage.patches == []
    assert storage.vocabulary_inbox[0].term == "come across"
    assert storage.vocabulary_inbox[0].status == "suggested"


@pytest.mark.asyncio
async def test_inbox_reverses_a_native_to_learning_language_lookup():
    storage = FakeStorage()
    sink = UserStorageVocabularyInboxSink(
        storage,
        clock=lambda: 42.0,
        identifier=lambda: "suggestion-1",
    )

    await sink.observe(
        observation(
            source_text="берег",
            translation="bank",
            source_language="ru",
            target_language="en",
            dictionary_form="берег",
            transcription="bʲerʲek",
        )
    )

    assert storage.vocabulary_inbox[0].term == "bank"
    assert storage.vocabulary_inbox[0].translation == "берег"
    assert storage.vocabulary_inbox[0].transcription == ""
