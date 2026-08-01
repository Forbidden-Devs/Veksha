from dataclasses import dataclass, field

import pytest

from api import reading_coach as coach_api
from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.dictionary import DictionaryDetails
from repositories.lexicon import LexiconRepository


@dataclass
class Settings:
    target_lang: str = "en"
    native_lang: str = "ru"
    english_level: str = "b1"


@dataclass
class Storage:
    settings: Settings = field(default_factory=Settings)
    lexicon: LexiconRepository = field(default_factory=lambda: LexiconRepository("tester"))
    saves: int = 0

    def save(self):
        self.saves += 1


class DictionaryService:
    async def execute(self, request):
        return DictionaryDetails(request.term, f"перевод {request.term}", "/ipa/")


def test_knowledge_aggregates_multiple_senses_without_order_dependence():
    storage = Storage(
        lexicon=LexiconRepository("tester", [
            LexicalItem("known-bank", "bank", "en", "банк", status="known"),
            LexicalItem("new-bank", "bank", "en", "берег", status="suggested"),
        ])
    )

    assert coach_api._knowledge(storage, "bank", "en") == "known"


@pytest.mark.asyncio
async def test_analysis_returns_actionable_obstacles(monkeypatch):
    storage = Storage()
    monkeypatch.setattr(coach_api, "get_storage", lambda _username: storage)

    response = await coach_api.analyze_reading(
        coach_api.ReadingCoachRequest(
            text=("ordinary " * 60) + ("photosynthesis " * 8)
        ),
        "tester",
    )

    assert response.unique_terms == 2
    assert response.obstacles[0].term == "photosynthesis"
    assert response.projected_known_pct > response.known_pct


@pytest.mark.asyncio
async def test_prepare_adds_only_terms_grounded_in_the_page(monkeypatch):
    storage = Storage()
    monkeypatch.setattr(coach_api, "get_storage", lambda _username: storage)
    monkeypatch.setattr(
        coach_api,
        "build_dictionary_enrichment",
        lambda: DictionaryService(),
    )

    response = await coach_api.prepare_reading(
        coach_api.PrepareReadingRequest(
            text="Photosynthesis converts light into chemical energy.",
            terms=["photosynthesis", "invented"],
            source_url="https://example.test/article?private=yes",
        ),
        "tester",
    )

    assert response.added == 1
    assert storage.lexicon.all()[0].term == "photosynthesis"
    assert storage.lexicon.all()[0].encounters[0].source_url == (
        "https://example.test/article"
    )
    assert storage.saves == 1
