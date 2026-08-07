from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

from api import pattern_workshop as api
from learning_core_v2.grammar_analysis import GrammarAnalysis, GrammarAnnotation
from repositories.grammar_memory import GrammarMemoryRepository


@dataclass
class Settings:
    target_lang: str = "en"
    native_lang: str = "ru"
    english_level: str = "b1"


@dataclass
class Storage:
    settings: Settings = field(default_factory=Settings)
    grammar: GrammarMemoryRepository = field(default_factory=GrammarMemoryRepository)
    saves: int = 0

    def save(self):
        self.saves += 1


class Analyzer:
    async def execute(self, _request):
        return GrammarAnalysis(annotations=(
            GrammarAnnotation(
                "has finished",
                "tense_aspect",
                "Present perfect",
                "Links the past to now.",
            ),
        ))


@pytest.mark.asyncio
async def test_analysis_is_an_expiring_draft_and_does_not_save(monkeypatch):
    storage = Storage()
    monkeypatch.setattr(api, "get_storage", lambda _username: storage)
    monkeypatch.setattr(api, "build_grammar_analyzer", Analyzer)

    response = await api.analyze_pattern_workshop(
        api.AnalyzeRequest(
            text="She has finished the article.",
            source_url="https://example.test/story?private=yes#section",
        ),
        "tester",
    )

    assert response.patterns[0].label == "Present perfect"
    assert storage.grammar.all() == ()
    assert storage.saves == 0


@pytest.mark.asyncio
async def test_skill_is_saved_only_after_successful_micro_practice(monkeypatch):
    storage = Storage()
    api._drafts.clear()
    monkeypatch.setattr(api, "get_storage", lambda _username: storage)
    monkeypatch.setattr(api, "build_grammar_analyzer", Analyzer)
    draft = await api.analyze_pattern_workshop(
        api.AnalyzeRequest(text="She has finished the article."),
        "tester",
    )

    with pytest.raises(HTTPException) as error:
        await api.complete_pattern_workshop(
            api.CompleteRequest(draft_id=draft.draft_id, pattern_index=0, answer="past"),
            "tester",
        )
    assert error.value.status_code == 422
    assert storage.grammar.all() == ()

    skill = await api.complete_pattern_workshop(
        api.CompleteRequest(
            draft_id=draft.draft_id,
            pattern_index=0,
            answer="Present perfect",
        ),
        "tester",
    )
    assert skill.practice_count == 1
    assert storage.grammar.all()[0].encounters[0].example == "She has finished the article."
    assert storage.saves == 1


@pytest.mark.asyncio
async def test_training_or_chat_error_enters_as_a_draft(monkeypatch):
    storage = Storage()
    api._drafts.clear()
    monkeypatch.setattr(api, "get_storage", lambda _username: storage)

    draft = await api.create_error_draft(
        api.ErrorDraftRequest(
            source="ai_correction",
            original="I asked where was she.",
            correction="I asked where she was.",
            category="word_order",
            label="Indirect question order",
            explanation="The subject comes before the verb.",
        ),
        "tester",
    )

    assert draft.patterns[0].contrast_example == (
        "I asked where was she. → I asked where she was."
    )
    assert storage.grammar.all() == ()
    assert storage.saves == 0
