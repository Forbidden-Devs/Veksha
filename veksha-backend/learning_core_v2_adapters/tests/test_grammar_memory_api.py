from dataclasses import dataclass, field

import pytest

from api import grammar_lens as grammar_api


@dataclass
class Settings:
    target_lang: str = "en"
    native_lang: str = "ru"
    english_level: str = "b1"


@dataclass
class Storage:
    settings: Settings = field(default_factory=Settings)
    grammar_memory: list = field(default_factory=list)
    saves: int = 0

    def save(self):
        self.saves += 1


@pytest.mark.asyncio
async def test_analysis_remembers_grounded_grammar_pattern(monkeypatch):
    storage = Storage()

    async def analyze(_text, _native_language, _level):
        return {
            "segments": [],
            "annotations": [
                {
                    "text": "has finished",
                    "category": "tense_aspect",
                    "label": "Present perfect",
                    "explanation": "Links the past to now.",
                }
            ],
        }

    monkeypatch.setattr(grammar_api, "get_storage", lambda _username: storage)
    monkeypatch.setattr(grammar_api, "analyze_grammar_block", analyze)

    response = await grammar_api.api_grammar_lens_analyze(
        grammar_api.GrammarLensRequest(
            blocks=["She has finished the article."],
            source_url="https://example.test/story?private=yes#section",
        ),
        "tester",
    )

    assert response.remembered == 1
    assert storage.grammar_memory[0].seen_count == 1
    assert storage.grammar_memory[0].encounters[0].source_url == (
        "https://example.test/story"
    )
    assert storage.saves == 1


@pytest.mark.asyncio
async def test_memory_status_can_be_changed(monkeypatch):
    storage = Storage()
    storage.grammar_memory = list(
        grammar_api.RememberGrammar().execute(
            [],
            grammar_api.GrammarObservation(
                language="en",
                category="word_order",
                label="Question order",
                explanation="Auxiliary before subject.",
                example="Did you read it?",
            ),
            item_id="pattern-1",
            observed_at=10,
        )
    )
    monkeypatch.setattr(grammar_api, "get_storage", lambda _username: storage)

    response = await grammar_api.api_grammar_memory_status(
        "pattern-1",
        grammar_api.GrammarMemoryStatusRequest(status="mastered"),
        "tester",
    )

    assert response.status == "mastered"
    assert storage.grammar_memory[0].status == "mastered"
    assert storage.saves == 1
