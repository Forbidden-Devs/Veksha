import json
from dataclasses import dataclass, replace

import pytest
from fastapi import WebSocketDisconnect

from api import training_v2
from learning_core_v2.acquisition import LexicalItem, ReviewSchedule
from learning_core_v2.practice import AnswerEvaluation, PracticeTask


def test_training_v2_preserves_public_paths():
    paths = {route.path for route in training_v2.router.routes}

    assert paths == {
        "/api/training/init",
        "/api/training/validate",
        "/api/training/review_log",
        "/api/training/ws",
    }


@dataclass
class FakeSettings:
    english_level: str = "b1"
    native_lang: str = "ru"
    target_lang: str = "en"


@dataclass
class FakeStorage:
    settings: FakeSettings
    lexicon: object | None = None

    def save(self):
        pass


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def receive_text(self):
        if not self.messages:
            raise WebSocketDisconnect()
        return json.dumps(self.messages.pop(0))

    async def send_json(self, value):
        self.sent.append(value)

    def of_type(self, message_type):
        return [message for message in self.sent if message["type"] == message_type]


class FakeRepository:
    def __init__(self, items=None):
        self._items = items or [
            LexicalItem(
                "item-run",
                "run",
                "en",
                "бежать",
                status="learning",
                schedule=ReviewSchedule(review_count=2, next_review_at=0),
            )
        ]
        self.graded = []

    def items(self):
        return list(self._items)

    def apply_grade(self, graded):
        self.graded.append(graded)
        return True

    def mark_known(self, _item_id):
        return False


class FakeBuilder:
    def __init__(self):
        self.plans = []

    async def execute(self, plan, **_settings):
        self.plans.append(plan)
        return PracticeTask(
            task_id=f"task-{len(self.plans)}",
            item_id=plan.item.item_id,
            word=plan.item.term,
            context=plan.item.latest_context,
            kind=plan.kind,
            skill=plan.skill,
            stage=plan.stage,
            question="Переведите слово run",
            review_count=plan.item.schedule.review_count,
            reason=plan.reason,
            expected_answer="бежать",
        )


class RecordingChecker:
    def __init__(self, evaluation=None):
        self.requests = []
        self._evaluation = evaluation or AnswerEvaluation("correct", "Верно")

    async def execute(self, request):
        self.requests.append(request)
        return self._evaluation


def wire(monkeypatch, repository, builder, checker):
    async def authenticated(_socket):
        return "tester"

    monkeypatch.setattr(training_v2, "ws_current_user", authenticated)
    monkeypatch.setattr(
        training_v2, "get_storage", lambda _username: FakeStorage(FakeSettings())
    )
    monkeypatch.setattr(
        training_v2,
        "LexiconPracticeRepository",
        lambda _lexicon, _commit: repository,
    )
    monkeypatch.setattr(
        training_v2, "build_practice_services", lambda: (builder, checker)
    )


@pytest.mark.asyncio
async def test_websocket_ignores_client_word_and_question_when_checking(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "request_task"},
            {
                "type": "answer",
                "task_id": "task-1",
                "word": "tampered",
                "question": "tampered",
                "answer": "бежать",
                "response_seconds": 12,
            },
            {"type": "commit", "task_id": "task-1"},
        ]
    )
    repository = FakeRepository()
    checker = RecordingChecker()
    wire(monkeypatch, repository, FakeBuilder(), checker)

    await training_v2.training_ws(socket)

    assert checker.requests[0].task.word == "run"
    assert checker.requests[0].task.question == "Переведите слово run"
    assert [message["type"] for message in socket.sent] == [
        "task",
        "result",
        "committed",
    ]


@pytest.mark.asyncio
async def test_task_message_carries_the_plan_but_not_the_target_word(monkeypatch):
    socket = FakeWebSocket([{"type": "request_task"}])
    wire(monkeypatch, FakeRepository(), FakeBuilder(), RecordingChecker())

    await training_v2.training_ws(socket)

    task = socket.of_type("task")[0]
    assert task["item_id"] == "item-run"
    assert task["skill"] in {"recognition", "recall", "contextual_meaning"}
    assert task["reason"]["code"]
    assert task["is_correction"] is False
    assert "word" not in task


@pytest.mark.asyncio
async def test_answer_suggests_a_rating_and_reveals_the_target_on_a_miss(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "request_task"},
            {
                "type": "answer",
                "task_id": "task-1",
                "answer": "идти",
                "response_seconds": 12,
            },
        ]
    )
    checker = RecordingChecker(AnswerEvaluation("incorrect", "Нет", "Спутано с идти"))
    wire(monkeypatch, FakeRepository(), FakeBuilder(), checker)

    await training_v2.training_ws(socket)

    result = socket.of_type("result")[0]
    assert result["suggested_rating"] == "again"
    assert result["expected_answer"] == "бежать"
    assert result["error_note"] == "Спутано с идти"


@pytest.mark.asyncio
async def test_nothing_is_scheduled_until_the_learner_commits(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "request_task"},
            {"type": "answer", "task_id": "task-1", "answer": "бежать"},
        ]
    )
    repository = FakeRepository()
    wire(monkeypatch, repository, FakeBuilder(), RecordingChecker())

    await training_v2.training_ws(socket)

    assert repository.graded == []


@pytest.mark.asyncio
async def test_commit_applies_the_manual_rating_over_the_suggestion(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "request_task"},
            {
                "type": "answer",
                "task_id": "task-1",
                "answer": "бежать",
                "response_seconds": 12,
            },
            {"type": "commit", "task_id": "task-1", "rating": "hard"},
        ]
    )
    repository = FakeRepository()
    wire(monkeypatch, repository, FakeBuilder(), RecordingChecker())

    await training_v2.training_ws(socket)

    assert [graded.rating for graded in repository.graded] == ["hard"]
    assert repository.graded[0].suggested_rating == "good"
    assert repository.graded[0].manual_rating is True
    committed = socket.of_type("committed")[0]
    assert committed["rating"] == "hard"
    assert committed["progress"] == {"done": 1, "target": 10}
    assert len(committed["skills"]) == 4


@pytest.mark.asyncio
async def test_a_miss_queues_a_corrective_task_on_the_same_skill(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "request_task"},
            {"type": "answer", "task_id": "task-1", "answer": "идти"},
            {"type": "commit", "task_id": "task-1"},
            {"type": "request_task"},
        ]
    )
    builder = FakeBuilder()
    checker = RecordingChecker(AnswerEvaluation("incorrect", "Нет"))
    wire(monkeypatch, FakeRepository(), builder, checker)

    await training_v2.training_ws(socket)

    committed = socket.of_type("committed")[0]
    assert committed["rating"] == "again"
    assert committed["correction"]["stage"] == "support"

    repair = socket.of_type("task")[1]
    assert repair["is_correction"] is True
    assert repair["stage"] == "support"
    assert repair["skill"] == committed["correction"]["skill"]


@pytest.mark.asyncio
async def test_listening_is_planned_only_for_a_client_that_can_speak(monkeypatch):
    listening_only = [
        replace(
            LexicalItem(
                "item-run",
                "run",
                "en",
                "бежать",
                status="learning",
                schedule=ReviewSchedule(review_count=2, next_review_at=0),
            ),
            skills=(
                LexicalItem("x", "x", "en", "x")
                .skills.record("recognition", "easy", now=1)
                .record("recognition", "easy", now=1)
                .record("recall", "easy", now=1)
                .record("recall", "easy", now=1)
                .record("contextual_meaning", "easy", now=1)
                .record("contextual_meaning", "easy", now=1)
            ),
        )
    ]
    socket = FakeWebSocket(
        [{"type": "init", "audio": True}, {"type": "request_task"}]
    )
    builder = FakeBuilder()
    wire(monkeypatch, FakeRepository(listening_only), builder, RecordingChecker())

    await training_v2.training_ws(socket)

    assert socket.of_type("session")[0]["audio"] is True
    assert builder.plans[0].skill == "listening"


@pytest.mark.asyncio
async def test_an_undraftable_task_re_plans_a_different_sense(monkeypatch):
    class RefusesFirstItem(FakeBuilder):
        async def execute(self, plan, **settings):
            if plan.item.item_id == "item-run":
                self.plans.append(plan)
                raise ValueError("options omit the expected answer")
            return await super().execute(plan, **settings)

    items = [
        LexicalItem(
            "item-run", "run", "en", "бежать",
            status="learning",
            schedule=ReviewSchedule(review_count=2, next_review_at=0),
        ),
        LexicalItem(
            "item-walk", "walk", "en", "идти",
            status="learning",
            schedule=ReviewSchedule(review_count=2, next_review_at=1),
        ),
    ]
    socket = FakeWebSocket([{"type": "request_task"}])
    builder = RefusesFirstItem()
    wire(monkeypatch, FakeRepository(items), builder, RecordingChecker())

    await training_v2.training_ws(socket)

    # The refused sense is retired rather than re-planned until the budget runs
    # out, so the learner still gets an exercise.
    assert [plan.item.item_id for plan in builder.plans] == ["item-run", "item-walk"]
    assert socket.of_type("task")[0]["item_id"] == "item-walk"
    assert socket.of_type("error") == []


@pytest.mark.asyncio
async def test_exhausted_session_reports_a_summary(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "init", "exclude": ["item-run"]},
            {"type": "request_task"},
        ]
    )
    wire(monkeypatch, FakeRepository(), FakeBuilder(), RecordingChecker())

    await training_v2.training_ws(socket)

    done = socket.of_type("done")[0]
    assert done["summary"]["reviewed"] == 0
    assert done["summary"]["items"] == []
