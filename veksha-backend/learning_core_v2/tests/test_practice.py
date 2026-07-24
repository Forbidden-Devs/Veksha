from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from learning_core_v2.practice import (
    AnswerCheckRequest,
    AnswerEvaluation,
    BuildPracticeTask,
    CheckPracticeAnswer,
    PracticeQueue,
    PracticeTask,
    PracticeWord,
    TaskDraft,
)


@dataclass
class FirstChoice:
    seen: list = field(default_factory=list)

    def choose(self, values):
        self.seen.append(list(values))
        return values[0]


@dataclass
class FixedIdentifiers:
    value: str = "task-1"

    def new(self):
        return self.value


@dataclass
class StubProvider:
    draft: TaskDraft = field(default_factory=lambda: TaskDraft("Translate this", "recall"))
    evaluation: AnswerEvaluation = field(
        default_factory=lambda: AnswerEvaluation("correct", "Well done")
    )
    draft_requests: list = field(default_factory=list)
    check_requests: list = field(default_factory=list)

    async def draft_task(self, request):
        self.draft_requests.append(request)
        return self.draft

    async def evaluate_answer(self, request):
        self.check_requests.append(request)
        return self.evaluation


def word(text, **overrides):
    values = {"text": text, "language": "en"}
    values.update(overrides)
    return PracticeWord(**values)


def test_queue_prioritizes_due_words_then_new_words():
    queue = PracticeQueue(review_horizon_seconds=100)
    words = [
        word("newer", review_count=-1, added_at=20),
        word("later", review_count=2, next_review_at=1_080),
        word("earlier", review_count=1, next_review_at=1_020),
        word("newer-first", review_count=-1, added_at=10),
        word("future", review_count=2, next_review_at=1_101),
        word("known", known=True),
        word("native", language="ru"),
    ]

    available = queue.available(words, learning_language="en-US", now=1_000)

    assert [item.text for item in available] == [
        "earlier",
        "later",
        "newer-first",
        "newer",
    ]


def test_queue_honors_case_insensitive_exclusions():
    queue = PracticeQueue(review_horizon_seconds=0)
    available = queue.available(
        [word("Run"), word("Walk")],
        learning_language="en",
        now=1_000,
        excluded={"RUN"},
    )

    assert [item.text for item in available] == ["Walk"]


@pytest.mark.asyncio
async def test_task_builder_omits_reverse_kind_without_saved_translation():
    provider = StubProvider()
    choices = FirstChoice()
    service = BuildPracticeTask(provider, choices, FixedIdentifiers())

    task = await service.execute(
        word("run"),
        proficiency="b1",
        native_language="ru",
        learning_language="en",
    )

    assert task.task_id == "task-1"
    assert task.kind == "translation"
    assert "reverse_translation" not in choices.seen[0]


@pytest.mark.asyncio
async def test_task_builder_allows_reverse_kind_with_translation():
    provider = StubProvider()
    choices = FirstChoice()
    service = BuildPracticeTask(provider, choices, FixedIdentifiers())

    await service.execute(
        word("run", translation="бежать"),
        proficiency="b1",
        native_language="ru",
        learning_language="en",
    )

    assert "reverse_translation" in choices.seen[0]


@pytest.mark.asyncio
async def test_blank_answer_is_garbage_without_provider_call():
    provider = StubProvider()
    checker = CheckPracticeAnswer(provider)
    task = PracticeTask("id", "run", "", "translation", "Question", -1, "recall")

    result = await checker.execute(
        AnswerCheckRequest(task, "  ", "b1", "ru", "en")
    )

    assert result.outcome == "garbage"
    assert result.should_update_schedule is False
    assert provider.check_requests == []
