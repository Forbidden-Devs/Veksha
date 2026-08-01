from learning_core_v2.acquisition import (
    LexicalItem,
    ReviewSchedule,
    VocabularyEncounter,
)
from learning_core_v2.grammar_memory import GrammarEncounter, GrammarMemoryItem
from models import UserSettings
from storage import UserStorage


def test_lexical_items_round_trip_with_independent_schedules(monkeypatch):
    stored = {}
    monkeypatch.setattr("storage.db.kb_set", lambda _username, data: stored.update(data))
    monkeypatch.setattr("storage.db.settings_set", lambda _username, _settings: None)
    source = UserStorage(
        username="tester",
        lexical_items=[
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
                status="learning",
                schedule=ReviewSchedule(
                    review_count=3, next_review_at=99, stability=4.2
                ),
            )
        ],
        settings=UserSettings(),
    )

    source.save()
    monkeypatch.setattr("storage.db.kb_get", lambda _username: stored)
    monkeypatch.setattr("storage.db.settings_get", lambda _username: {})

    loaded = UserStorage.load("tester")

    assert loaded.lexical_items == source.lexical_items
    assert "words" not in stored
    assert "vocabulary_inbox" not in stored


def test_legacy_word_schedule_is_cloned_to_each_known_sense(monkeypatch):
    stored = {}
    legacy = {
        "words": [
            {
                "name": "bank",
                "language": "",
                "translation": "банк · берег",
                "counter": 4,
                "next_review": 123,
                "added_at": 10,
                "stability": 6.5,
                "difficulty": 3.2,
            }
        ],
        "vocabulary_inbox": [
            {
                "item_id": "bank-finance",
                "term": "bank",
                "language": "en",
                "translation": "банк",
                "status": "learning",
            },
            {
                "item_id": "bank-river",
                "term": "bank",
                "language": "en",
                "translation": "берег",
                "status": "learning",
            },
        ],
        "lesson_topics": [],
    }
    monkeypatch.setattr("storage.db.kb_get", lambda _username: legacy)
    monkeypatch.setattr("storage.db.settings_get", lambda _username: {"target_lang": "en"})
    monkeypatch.setattr("storage.db.kb_set", lambda _username, data: stored.update(data))
    monkeypatch.setattr("storage.db.settings_set", lambda _username, _settings: None)

    loaded = UserStorage.load("tester")

    assert [item.item_id for item in loaded.lexical_items] == [
        "bank-finance",
        "bank-river",
    ]
    assert [item.schedule.review_count for item in loaded.lexical_items] == [4, 4]
    assert loaded.lexical_items[0].schedule is not loaded.lexical_items[1].schedule
    assert stored["schema_version"] == 2
    assert "words" not in stored


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
