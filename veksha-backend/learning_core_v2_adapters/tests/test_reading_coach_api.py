from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from api import reading_coach as coach_api
from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.dictionary import DictionaryDetails
from learning_core_v2.reading_coach import ReadingAnswerEvaluation
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
    assert response.structure_cefr in {"A1", "A2", "B1", "B2", "C1"}
    assert response.average_sentence_words > 0


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


class QuestionBuilder:
    async def execute(self, request):
        return "What happened?"


class AnswerChecker:
    async def execute(self, request):
        return ReadingAnswerEvaluation("correct", "Верно")


@pytest.mark.asyncio
async def test_comprehension_question_is_private_to_the_user(monkeypatch):
    coach_api._questions.clear()
    monkeypatch.setattr(coach_api, "get_storage", lambda _username: Storage())
    monkeypatch.setattr(
        coach_api,
        "build_reading_comprehension_services",
        lambda: (QuestionBuilder(), AnswerChecker()),
    )
    created = await coach_api.create_comprehension_question(
        coach_api.ComprehensionQuestionRequest(
            text="A complete paragraph with enough information for a comprehension question."
        ),
        "tester",
    )

    with pytest.raises(coach_api.HTTPException) as error:
        await coach_api.check_comprehension_answer(
            coach_api.ComprehensionAnswerRequest(
                question_id=created.question_id,
                answer="Something happened",
            ),
            "another-user",
        )

    assert error.value.status_code == 404

    checked = await coach_api.check_comprehension_answer(
        coach_api.ComprehensionAnswerRequest(
            question_id=created.question_id,
            answer="Something happened",
        ),
        "tester",
    )
    assert checked.outcome == "correct"


class ExplanationService:
    async def execute(self, request):
        return SimpleNamespace(explanation="Подсказка без раскрытия ответа")


@pytest.mark.asyncio
async def test_paragraph_help_does_not_write_to_vocabulary(monkeypatch):
    storage = Storage()
    monkeypatch.setattr(coach_api, "get_storage", lambda _username: storage)
    monkeypatch.setattr(
        coach_api,
        "build_deferred_translate_text",
        lambda _storage: (object(), object(), object()),
    )
    monkeypatch.setattr(coach_api, "build_explain_text", lambda: ExplanationService())

    async def translate(*_args, **_kwargs):
        return SimpleNamespace(translation="Перевод абзаца")

    monkeypatch.setattr(coach_api, "_execute_translation", translate)
    result = await coach_api.help_with_paragraph(
        coach_api.ParagraphHelpRequest(
            text="This is a complete paragraph with enough detail to explain its meaning."
        ),
        "tester",
    )

    assert result.translation == "Перевод абзаца"
    assert result.explanation == "Подсказка без раскрытия ответа"
    assert storage.lexicon.all() == ()
