"""Adding a tracked word creates a complete, idempotent dictionary entry."""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MemoryStorage:
    def __init__(self):
        self.settings = SimpleNamespace(target_lang="en", native_lang="ru", english_level="a2")
        self.lexical_items = []

    def find_lexical_item_by_term(self, name: str):
        normalized = name.strip().casefold()
        return next(
            (item for item in self.lexical_items if item.term.casefold() == normalized),
            None,
        )

    def save(self):
        pass


def test_add_kb_word_populates_details_and_does_not_duplicate():
    # Importing API modules during pytest collection loads config before
    # test_billing can install its test secrets. Keep this import lazy so the
    # whole backend suite remains independent of module collection order.
    import api.settings as settings_api

    storage = MemoryStorage()
    calls = 0

    class Enrichment:
        async def execute(self, request):
            from learning_core_v2.dictionary import DictionaryDetails

            nonlocal calls
            calls += 1
            assert request.term == "serendipity"
            return DictionaryDetails(
                "serendipity", "счастливая случайность", "/ˌserənˈdɪpəti/"
            )

    with (
        patch.object(settings_api, "get_storage", return_value=storage),
        patch.object(
            settings_api, "build_dictionary_enrichment", return_value=Enrichment()
        ),
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
    assert [item.term for item in storage.lexical_items].count("serendipity") == 1


if __name__ == "__main__":
    test_add_kb_word_populates_details_and_does_not_duplicate()
    print("PASS add tracked word")
