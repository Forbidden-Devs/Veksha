from learning_core_v2.acquisition import LexicalItem, VocabularyEncounter
from learning_core_v2.grammar_memory import GrammarEncounter, GrammarMemoryItem
from models import UserSettings
from storage import UserStorage


def test_vocabulary_inbox_round_trips_in_the_user_document(monkeypatch):
    stored = {}
    monkeypatch.setattr("storage.db.kb_set", lambda _username, data: stored.update(data))
    monkeypatch.setattr("storage.db.settings_set", lambda _username, _settings: None)
    source = UserStorage(
        username="tester",
        vocabulary_inbox=[
            LexicalItem(
                "item-1",
                "come across",
                "en",
                "случайно найти",
                encounters=(
                    VocabularyEncounter(
                        "I came across it.",
                        "https://example.test/story",
                        42.0,
                    ),
                ),
            )
        ],
        settings=UserSettings(),
    )

    source.save()
    monkeypatch.setattr("storage.db.kb_get", lambda _username: stored)
    monkeypatch.setattr("storage.db.settings_get", lambda _username: {})

    loaded = UserStorage.load("tester")

    assert loaded.vocabulary_inbox == source.vocabulary_inbox


def test_grammar_memory_round_trips_in_the_user_document(monkeypatch):
    stored = {}
    monkeypatch.setattr("storage.db.kb_set", lambda _username, data: stored.update(data))
    monkeypatch.setattr("storage.db.settings_set", lambda _username, _settings: None)
    source = UserStorage(
        username="tester",
        grammar_memory=[
            GrammarMemoryItem(
                item_id="pattern-1",
                language="en",
                category="tense_aspect",
                label="Present perfect",
                explanation="Links the past to now.",
                seen_count=2,
                first_seen_at=10,
                last_seen_at=20,
                encounters=(
                    GrammarEncounter(
                        "She has finished.",
                        "https://example.test/story",
                        20,
                    ),
                ),
            )
        ],
        settings=UserSettings(),
    )

    source.save()
    monkeypatch.setattr("storage.db.kb_get", lambda _username: stored)
    monkeypatch.setattr("storage.db.settings_get", lambda _username: {})

    loaded = UserStorage.load("tester")

    assert loaded.grammar_memory == source.grammar_memory
