from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from learning_core_v2.dictionary import DictionaryLookupRequest
from learning_core_v2.explanation import ExplanationRequest
from learning_core_v2.immersion import BlockAnalysisRequest, ImmersionContext
from learning_core_v2.lesson import (
    AnswerRequest as LessonAnswerRequest,
    CurriculumRequest,
    LearnerProfile,
    LessonMaterial,
    LessonSection,
    LessonUnit,
    MaterialRequest,
    QuestionRequest,
)
from learning_core_v2.practice import (
    AnswerCheckRequest,
    PracticeTask,
    PracticeWord,
    TaskDraftRequest,
)
from learning_core_v2.translation import TranslationRequest
from learning_core_v2_adapters.openai_responses import (
    LanguageProviderError,
    OpenAIResponsesLanguageProvider,
)


@dataclass
class StubTransport:
    response: dict[str, Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def post(self, url, *, headers, payload, timeout_seconds):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


def completed_response(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(value)}
                ],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
    }


@pytest.mark.asyncio
async def test_translation_uses_responses_structured_output_contract():
    transport = StubTransport(
        completed_response(
            {
                "translation": "бежать",
                "detected_source_language": "en",
                "is_lexical_unit": True,
                "dictionary_form": "run",
                "transcription": "rʌn",
            }
        )
    )
    usage = []
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key",
        model="test-model",
        transport=transport,
        usage_recorder=lambda *args: usage.append(args),
    )

    result = await provider.translate(
        TranslationRequest("run", "auto", "ru", "b1")
    )

    assert result.dictionary_form == "run"
    payload = transport.calls[0]["payload"]
    assert payload["model"] == "test-model"
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["store"] is False
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert json.loads(payload["input"])["text"] == "run"
    assert usage[0][0:2] == ("core_v2_translate", "test-model")


@pytest.mark.asyncio
async def test_dictionary_lookup_has_its_own_structured_contract():
    transport = StubTransport(
        completed_response(
            {
                "headword": "serendipity",
                "translation": "счастливая случайность",
                "transcription": "/ˌserənˈdɪpəti/",
            }
        )
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )

    result = await provider.lookup_dictionary_entry(
        DictionaryLookupRequest("serendipity", "en", "ru", "a2", "A discovery")
    )

    assert result.headword == "serendipity"
    assert result.translation == "счастливая случайность"
    payload = transport.calls[0]["payload"]
    assert payload["text"]["format"]["name"] == "dictionary_entry"
    sent = json.loads(payload["input"])
    assert sent["term"] == "serendipity"
    assert sent["context"] == "A discovery"


@pytest.mark.asyncio
async def test_explanation_uses_separate_schema():
    transport = StubTransport(completed_response({"explanation": "Глагол движения."}))
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )

    result = await provider.explain(
        ExplanationRequest("run", "бежать", "b1", "ru", "en")
    )

    assert result == "Глагол движения."
    assert transport.calls[0]["payload"]["text"]["format"]["name"] == "explanation_result"


@pytest.mark.asyncio
async def test_refusal_is_reported_as_provider_error():
    transport = StubTransport(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "No"}],
                }
            ],
        }
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )

    with pytest.raises(LanguageProviderError, match="refused"):
        await provider.translate(TranslationRequest("run", "en", "ru", "b1"))


@pytest.mark.asyncio
async def test_missing_key_is_rejected_before_transport_call():
    transport = StubTransport(completed_response({}))
    provider = OpenAIResponsesLanguageProvider(
        api_key="", model="test-model", transport=transport
    )

    with pytest.raises(LanguageProviderError, match="OPENAI_API_KEY"):
        await provider.translate(TranslationRequest("run", "en", "ru", "b1"))

    assert transport.calls == []


@pytest.mark.asyncio
async def test_practice_task_uses_its_own_structured_schema():
    transport = StubTransport(
        completed_response(
            {"question": "Переведите run", "skill": "Recall", "reverse_text": ""}
        )
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )

    draft = await provider.draft_task(
        TaskDraftRequest(
            PracticeWord("run", "en", translation="бежать"),
            "translation",
            "b1",
            "ru",
            "en",
        )
    )

    assert draft.question == "Переведите run"
    payload = transport.calls[0]["payload"]
    assert payload["text"]["format"]["name"] == "practice_task"
    assert payload["reasoning"] == {"effort": "none"}


@pytest.mark.asyncio
async def test_answer_check_includes_server_task_and_reverse_cue():
    transport = StubTransport(
        completed_response({"outcome": "correct", "feedback": "Верно"})
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )
    task = PracticeTask(
        "id", "run", "context", "reverse_translation", "Назовите слово", 1, "Recall", "бежать"
    )

    result = await provider.evaluate_answer(
        AnswerCheckRequest(task, "run", "b1", "ru", "en")
    )

    assert result.outcome == "correct"
    sent = json.loads(transport.calls[0]["payload"]["input"])
    assert sent["word"] == "run"
    assert sent["reverse_text"] == "бежать"


@pytest.mark.asyncio
async def test_lesson_curriculum_uses_separate_call_and_limits_units():
    transport = StubTransport(completed_response({"units": ["One", "Two", "Three"]}))
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )
    profile = LearnerProfile("b1", "ru", "en", "travel")

    units = await provider.propose_units(
        CurriculumRequest("Small talk", (), 2, profile)
    )

    assert units == ["One", "Two"]
    payload = transport.calls[0]["payload"]
    assert payload["text"]["format"]["name"] == "lesson_curriculum"
    assert json.loads(payload["input"])["learner_goals"] == "travel"


@pytest.mark.asyncio
async def test_lesson_material_maps_structured_sections():
    transport = StubTransport(
        completed_response(
            {
                "title": "Introductions",
                "intro": "Start here.",
                "sections": [
                    {
                        "icon": "💬",
                        "header": "Pattern",
                        "items": ["Hello, I am …"],
                        "text": "",
                        "highlight": True,
                    }
                ],
            }
        )
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )

    material = await provider.write_material(
        MaterialRequest(
            "Small talk",
            "Introductions",
            ("Introductions",),
            LearnerProfile("b1", "ru", "en"),
        )
    )

    assert material.sections[0].items == ("Hello, I am …",)
    assert material.sections[0].highlight is True


@pytest.mark.asyncio
async def test_lesson_question_and_check_include_server_material():
    profile = LearnerProfile("b1", "ru", "en")
    material = LessonMaterial(
        "Introductions",
        "Start here.",
        (LessonSection("Pattern", items=("Hello, I am …",)),),
    )
    unit = LessonUnit("Introductions", material)
    question_transport = StubTransport(
        completed_response({"question": "Как представиться?"})
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=question_transport
    )

    question = await provider.write_question(
        QuestionRequest("Small talk", unit, (), profile)
    )

    assert question == "Как представиться?"
    sent = json.loads(question_transport.calls[0]["payload"]["input"])
    assert sent["material"]["title"] == "Introductions"

    check_transport = StubTransport(
        completed_response({"outcome": "correct", "feedback": "Верно"})
    )
    checker = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=check_transport
    )
    result = await checker.evaluate_lesson_answer(
        LessonAnswerRequest("Small talk", unit, question, "Hello, I am Sam", profile)
    )

    assert result.outcome == "correct"
    assert json.loads(check_transport.calls[0]["payload"]["input"])["learner_answer"] == (
        "Hello, I am Sam"
    )


@pytest.mark.asyncio
async def test_immersion_analysis_uses_exact_text_structured_contract():
    transport = StubTransport(
        completed_response(
            {
                "sentences": [
                    {
                        "text": "A useful sentence.",
                        "cefr": "B1",
                        "translation": "Полезное предложение.",
                    }
                ]
            }
        )
    )
    provider = OpenAIResponsesLanguageProvider(
        api_key="test-key", model="test-model", transport=transport
    )

    result = await provider.analyze_block(
        BlockAnalysisRequest(
            "A useful sentence.", ImmersionContext("en", "ru", "B1")
        )
    )

    assert result[0].translation == "Полезное предложение."
    payload = transport.calls[0]["payload"]
    assert payload["text"]["format"]["name"] == "immersion_analysis"
    sent = json.loads(payload["input"])
    assert sent["page_block"] == "A useful sentence."
    assert sent["learner_cefr"] == "B1"
