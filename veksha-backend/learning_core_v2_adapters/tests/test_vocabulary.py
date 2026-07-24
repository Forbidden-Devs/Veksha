from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from learning_core_v2.translation import VocabularyObservation
from learning_core_v2_adapters.vocabulary import UserStorageVocabularySink


@dataclass
class FakeSettings:
    target_lang: str = "en"


@dataclass
class FakeWord:
    name: str
    translation: str = ""
    transcription: str = ""


@dataclass
class FakeStorage:
    settings: FakeSettings = field(default_factory=FakeSettings)
    words: dict[str, FakeWord] = field(default_factory=dict)
    patches: list = field(default_factory=list)
    saves: int = 0

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


@pytest.mark.asyncio
async def test_adds_lookup_in_the_learning_language():
    storage = FakeStorage()

    await UserStorageVocabularySink(storage).observe(observation())

    assert storage.patches[0].value == "run"
    assert storage.patches[0].counter == 0
    assert storage.words["run"].translation == "бежать"
    assert storage.words["run"].transcription == "rʌn"
    assert storage.saves == 1


@pytest.mark.asyncio
async def test_does_not_add_native_language_or_phrase_lookups():
    storage = FakeStorage()
    sink = UserStorageVocabularySink(storage)

    await sink.observe(observation(source_language="ru"))
    await sink.observe(observation(is_lexical_unit=False, dictionary_form=""))

    assert storage.patches == []
    assert storage.saves == 0
