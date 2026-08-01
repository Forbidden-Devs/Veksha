from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

from api import vocabulary_inbox as inbox_api
from learning_core_v2.acquisition import LexicalItem, VocabularyEncounter
from repositories.lexicon import LexiconRepository


@dataclass
class FakeSettings:
    target_lang: str = "en"


@dataclass
class FakeStorage:
    settings: FakeSettings = field(default_factory=FakeSettings)
    lexicon: LexiconRepository = field(default_factory=lambda: LexiconRepository("tester"))
    saves: int = 0

    def save(self):
        self.saves += 1


def item(item_id="one", status="suggested"):
    return LexicalItem(
        item_id,
        "come across",
        "en",
        "случайно найти",
        "/kʌm əˈkrɒs/",
        status,
        (VocabularyEncounter("I came across it.", "https://example.test", 10.0),),
    )


@pytest.mark.asyncio
async def test_lists_only_pending_items_for_the_active_language(monkeypatch):
    storage = FakeStorage(
        lexicon=LexiconRepository("tester", [
            item(),
            item("ignored", "ignored"),
            LexicalItem("other", "hola", "es", "привет"),
        ])
    )
    monkeypatch.setattr(inbox_api, "get_storage", lambda _username: storage)

    response = await inbox_api.vocabulary_inbox("tester")

    assert [entry.item_id for entry in response.items] == ["one"]
    assert response.items[0].encounter_count == 1


@pytest.mark.asyncio
async def test_learn_moves_the_suggestion_into_the_training_pool(monkeypatch):
    storage = FakeStorage(lexicon=LexiconRepository("tester", [item()]))
    monkeypatch.setattr(inbox_api, "get_storage", lambda _username: storage)

    response = await inbox_api.decide_vocabulary_inbox_item(
        "one", inbox_api.InboxDecisionRequest(decision="learn"), "tester"
    )

    assert response.status == "learning"
    assert storage.lexicon.all()[0].translation == "случайно найти"
    assert storage.lexicon.all()[0].status == "learning"
    assert storage.lexicon.all()[0].schedule.added_at > 0


@pytest.mark.asyncio
async def test_known_records_knowledge_without_adding_a_review(monkeypatch):
    storage = FakeStorage(lexicon=LexiconRepository("tester", [item()]))
    monkeypatch.setattr(inbox_api, "get_storage", lambda _username: storage)

    response = await inbox_api.decide_vocabulary_inbox_item(
        "one", inbox_api.InboxDecisionRequest(decision="known"), "tester"
    )

    assert response.status == "known"
    assert storage.lexicon.all()[0].status == "known"


@pytest.mark.asyncio
async def test_decided_item_cannot_be_decided_twice(monkeypatch):
    storage = FakeStorage(lexicon=LexiconRepository("tester", [item(status="ignored")]))
    monkeypatch.setattr(inbox_api, "get_storage", lambda _username: storage)

    with pytest.raises(HTTPException) as raised:
        await inbox_api.decide_vocabulary_inbox_item(
            "one", inbox_api.InboxDecisionRequest(decision="learn"), "tester"
        )

    assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_another_sense_keeps_its_own_training_unit(monkeypatch):
    storage = FakeStorage(
        lexicon=LexiconRepository("tester", [
            LexicalItem("first", "bank", "en", "банк", status="learning"),
            LexicalItem("second", "bank", "en", "берег"),
        ]),
    )
    monkeypatch.setattr(inbox_api, "get_storage", lambda _username: storage)

    await inbox_api.decide_vocabulary_inbox_item(
        "second", inbox_api.InboxDecisionRequest(decision="learn"), "tester"
    )

    assert [(item.item_id, item.translation, item.status) for item in storage.lexicon.all()] == [
        ("first", "банк", "learning"),
        ("second", "берег", "learning"),
    ]
