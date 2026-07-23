"""Adding a tracked word creates a complete, idempotent dictionary entry."""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.settings as settings_api  # noqa: E402
from models import Word  # noqa: E402


class MemoryStorage:
    def __init__(self):
        self.settings = SimpleNamespace(target_lang="en", native_lang="ru", english_level="a2")
        self.words: list[Word] = []

    def find_word(self, name: str):
        normalized = name.strip().casefold()
        return next((word for word in self.words if word.name.casefold() == normalized), None)

    def apply_kb_changes(self, patches):
        for item in patches:
            if item.type == "add_word" and self.find_word(item.value) is None:
                self.words.append(Word(name=item.value, language="en", counter=item.counter))
            elif item.type == "delete_word":
                entry = self.find_word(item.value)
                if entry is not None:
                    self.words.remove(entry)
        return []

    def save(self):
        pass


def test_add_kb_word_populates_details_and_does_not_duplicate():
    storage = MemoryStorage()
    calls = 0

    async def fake_translate(text, source_lang, target_lang, level):
        nonlocal calls
        calls += 1
        assert (text, source_lang, target_lang, level) == ("serendipity", "en", "ru", "a2")
        return {"translation": "счастливая случайность", "transcription": "/ˌserənˈdɪpəti/"}

    with (
        patch.object(settings_api, "get_storage", return_value=storage),
        patch.object(settings_api.llm, "translate_selection", fake_translate),
    ):
        first = asyncio.run(settings_api.api_add_kb_word(
            settings_api.AddWordRequest(word="  Serendipity  "), "test-user",
        ))
        second = asyncio.run(settings_api.api_add_kb_word(
            settings_api.AddWordRequest(word="serendipity"), "test-user",
        ))

    assert first.translation == "счастливая случайность"
    assert first.transcription == "/ˌserənˈdɪpəti/"
    assert second == first
    assert calls == 1
    assert [word.name for word in storage.words].count("serendipity") == 1


if __name__ == "__main__":
    test_add_kb_word_populates_details_and_does_not_duplicate()
    print("PASS add tracked word")
