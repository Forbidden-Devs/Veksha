from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

import pytest
from fastapi import WebSocketDisconnect

from api import goal_v2
from learning_core_v2.goal import (
    DiscoveredPattern,
    DiscoveredTerm,
    Evidence,
    GoalMaterial,
    GoalReport,
    GoalRoute,
    GoalStep,
    LearnerProfile,
    RecordEvidence,
    StepEvaluation,
    StepMaterial,
    StepSection,
    SuccessCriterion,
    state_goal,
)
from learning_core_v2_adapters.runtime import GoalServices
from repositories.goals import GoalRepository


PROFILE = LearnerProfile("b1", "ru", "en", minutes=15)
CRITERIA = (
    SuccessCriterion("c1", "Узнать форму", 1),
    SuccessCriterion("c2", "Объяснить последовательность", 2),
    SuccessCriterion("c3", "Отличить от Past Simple", 3),
    SuccessCriterion("c4", "Использовать в новом рассказе", 4),
)
MATERIAL = StepMaterial("Порядок", "Интро", (StepSection("Пример", text="he had left"),))


def test_goal_router_exposes_the_goal_paths():
    paths = {route.path for route in goal_v2.router.routes}

    assert paths == {
        "/api/learning-goals",
        "/api/learning-goals/{goal_id}",
        "/api/learning-goals/ws",
    }


@dataclass
class FakeSettings:
    english_level: str = "b1"
    native_lang: str = "ru"
    target_lang: str = "en"
    language_settings: dict = field(default_factory=lambda: {
        "en": {"level": "b1", "goals": "", "prompt": "", "literacy_stage": "learning"}
    })

    @property
    def literacy_stage(self):
        return self.language_settings[self.target_lang].get("literacy_stage", "")


@dataclass
class FakeLexicon:
    items: tuple = ()

    def all(self):
        return self.items

    def replace_all(self, values):
        self.items = tuple(values)


@dataclass
class FakeGrammar:
    items: list = field(default_factory=list)

    def all(self):
        return tuple(self.items)

    def replace_all(self, values):
        self.items = list(values)


@dataclass
class FakeStorage:
    settings: FakeSettings
    goals: GoalRepository
    lexicon: FakeLexicon = field(default_factory=FakeLexicon)
    grammar: FakeGrammar = field(default_factory=FakeGrammar)
    saves: int = 0

    def save(self):
        self.saves += 1


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


class FakeFramer:
    async def execute(self, goal):
        return replace(goal, criteria=CRITERIA)


class RecordingStepBuilder:
    def __init__(self):
        self.plans = []
        self.count = 0

    async def execute(self, goal, plan, *, previous_questions=()):
        self.plans.append(plan)
        self.count += 1
        return GoalStep(
            step_id=f"step-{self.count}",
            criterion_id=plan.criterion_id,
            activity=plan.activity,
            reason=plan.reason,
            material=MATERIAL,
            question=f"Вопрос {self.count}",
        )


class RecordingChecker:
    def __init__(self, evaluation):
        self.evaluation = evaluation
        self.calls = []

    async def execute(self, goal, step, answer):
        self.calls.append((step, answer))
        return self.evaluation


class FakeCloser:
    async def execute(self, goal):
        return GoalReport(
            goal_id=goal.goal_id,
            statement=goal.statement,
            achieved=False,
            stopped_on_time=False,
            narrative="Итог",
            next_goal="Следующая цель",
            proven=(),
            shaky=(),
            examples=("he had left",),
            terms=goal.terms,
            patterns=goal.patterns,
        )


def install(monkeypatch, storage, *, checker, builder=None):
    builder = builder or RecordingStepBuilder()

    async def authenticated(_socket):
        return "tester"

    monkeypatch.setattr(goal_v2, "ws_current_user", authenticated)
    monkeypatch.setattr(goal_v2, "get_storage", lambda _username: storage)
    services = GoalServices(
        framer=FakeFramer(),
        route=GoalRoute(),
        step_builder=builder,
        answer_checker=checker,
        closer=FakeCloser(),
    )
    monkeypatch.setattr(goal_v2, "build_goal_services", lambda: services)
    return builder


@pytest.mark.asyncio
async def test_a_new_goal_is_framed_before_the_first_step(monkeypatch):
    storage = FakeStorage(FakeSettings(), GoalRepository())
    checker = RecordingChecker(
        StepEvaluation("correct", "transfers_confidently", "Верно")
    )
    builder = install(monkeypatch, storage, checker=checker)
    socket = FakeWebSocket(
        [
            {"type": "init", "statement": "Понять Past Perfect в рассказах"},
            {"type": "next_step"},
        ]
    )

    await goal_v2.goal_ws(socket)

    assert [message["type"] for message in socket.sent] == ["goal", "step"]
    assert len(socket.sent[0]["criteria"]) == 4
    assert socket.sent[0]["resumed"] is False
    # The opening step probes near the top of the goal, not at the basics.
    assert builder.plans[0].reason == "diagnose"
    assert builder.plans[0].criterion_id == "c3"


@pytest.mark.asyncio
async def test_the_next_step_follows_from_the_answer_not_a_fixed_list(monkeypatch):
    goal = replace(
        state_goal("Понять Past Perfect", PROFILE, material=GoalMaterial("Он ушёл.")),
        criteria=CRITERIA,
    )
    storage = FakeStorage(FakeSettings(), GoalRepository([goal]))
    checker = RecordingChecker(
        StepEvaluation("incorrect", "unknown_term", "Слово мешает")
    )
    builder = install(monkeypatch, storage, checker=checker)
    socket = FakeWebSocket(
        [
            {"type": "init", "goal_id": goal.goal_id},
            {"type": "next_step"},
            {
                "type": "answer",
                "step_id": "step-1",
                "criterion_id": "tampered",
                "answer": "не знаю",
            },
            {"type": "next_step"},
        ]
    )

    await goal_v2.goal_ws(socket)

    # The client's echoed criterion is ignored; the server's own step is judged.
    assert checker.calls[0][0].criterion_id == "c3"
    # A blocking word sends the route down to the shallowest untested criterion.
    assert builder.plans[1].criterion_id == "c1"
    assert builder.plans[1].reason == "nearest_gap"
    result = next(item for item in socket.sent if item["type"] == "result")
    assert result["cause"] == "unknown_term"
    assert {item["criterion_id"]: item["status"] for item in result["criteria"]}["c3"] == (
        "gap"
    )


@pytest.mark.asyncio
async def test_a_reopened_goal_resumes_from_its_stored_evidence(monkeypatch):
    goal = replace(
        state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA
    )
    goal = RecordEvidence(GoalRoute()).execute(
        goal,
        GoalStep("old", "c3", "compare_forms", "diagnose", MATERIAL, "Прошлый вопрос"),
        StepEvaluation("correct", "transfers_confidently", "Верно"),
        observed_at=10.0,
    )
    storage = FakeStorage(FakeSettings(), GoalRepository([goal]))
    builder = install(
        monkeypatch,
        storage,
        checker=RecordingChecker(StepEvaluation("correct", "unclear", "ok")),
    )
    socket = FakeWebSocket(
        [{"type": "init", "goal_id": goal.goal_id}, {"type": "next_step"}]
    )

    await goal_v2.goal_ws(socket)

    assert socket.sent[0]["resumed"] is True
    statuses = {item["criterion_id"]: item["status"] for item in socket.sent[0]["criteria"]}
    assert statuses["c1"] == "implied"
    # Resuming continues the route rather than re-diagnosing from scratch.
    assert builder.plans[0].reason != "diagnose"


@pytest.mark.asyncio
async def test_off_task_input_is_not_written_into_the_evidence(monkeypatch):
    goal = replace(state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA)
    storage = FakeStorage(FakeSettings(), GoalRepository([goal]))
    checker = RecordingChecker(StepEvaluation("garbage", "unclear", "Ответьте на вопрос"))
    install(monkeypatch, storage, checker=checker)
    socket = FakeWebSocket(
        [
            {"type": "init", "goal_id": goal.goal_id},
            {"type": "next_step"},
            {"type": "answer", "step_id": "step-1", "answer": "?????"},
            {"type": "answer", "step_id": "step-1", "answer": "теперь всерьёз"},
        ]
    )

    await goal_v2.goal_ws(socket)

    # The step stays open, so the learner answers it again.
    assert len(checker.calls) == 2
    assert storage.goals.find(goal.goal_id).evidence == ()


@pytest.mark.asyncio
async def test_closing_a_goal_files_what_the_lesson_surfaced(monkeypatch):
    goal = replace(state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA)
    storage = FakeStorage(FakeSettings(), GoalRepository([goal]))
    checker = RecordingChecker(
        StepEvaluation(
            "correct",
            "transfers_confidently",
            "Верно",
            terms=(DiscoveredTerm("had left", "уже ушёл", "he had left"),),
            patterns=(
                DiscoveredPattern("tense_aspect", "Past Perfect", "Раньше", "he had left"),
            ),
        )
    )
    install(monkeypatch, storage, checker=checker)
    socket = FakeWebSocket(
        [
            {"type": "init", "goal_id": goal.goal_id},
            {"type": "next_step"},
            {"type": "answer", "step_id": "step-1", "answer": "он ушёл раньше"},
            {"type": "finish"},
        ]
    )

    await goal_v2.goal_ws(socket)

    summary = next(item for item in socket.sent if item["type"] == "summary")
    assert summary["next_goal"] == "Следующая цель"
    assert summary["examples"] == ["he had left"]
    # New vocabulary arrives as a suggestion, never as decided knowledge.
    assert [item.term for item in storage.lexicon.all()] == ["had left"]
    assert [item.status for item in storage.lexicon.all()] == ["suggested"]
    assert [item.label for item in storage.grammar.all()] == ["Past Perfect"]


@pytest.mark.asyncio
async def test_finishing_an_alphabet_course_makes_transcription_optional(monkeypatch):
    criterion = SuccessCriterion("letters", "Read a fresh word", 4)
    evidence = (
        Evidence("letters", "apply_unaided", "correct", "transfers_confidently", "Q1", "A1"),
        Evidence("letters", "apply_unaided", "correct", "transfers_confidently", "Q2", "A2"),
    )
    goal = replace(
        state_goal("Learn the alphabet", PROFILE, kind="alphabet"),
        criteria=(criterion,),
        evidence=evidence,
    )
    settings = FakeSettings()
    storage = FakeStorage(settings, GoalRepository([goal]))
    install(
        monkeypatch,
        storage,
        checker=RecordingChecker(StepEvaluation("correct", "unclear", "ok")),
    )
    socket = FakeWebSocket(
        [{"type": "init", "goal_id": goal.goal_id}, {"type": "next_step"}]
    )

    await goal_v2.goal_ws(socket)

    assert settings.literacy_stage == "mastered"
    assert socket.sent[-1]["type"] == "summary"


@pytest.mark.asyncio
async def test_an_answer_to_an_expired_step_is_refused(monkeypatch):
    goal = replace(state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA)
    storage = FakeStorage(FakeSettings(), GoalRepository([goal]))
    install(
        monkeypatch,
        storage,
        checker=RecordingChecker(StepEvaluation("correct", "unclear", "ok")),
    )
    socket = FakeWebSocket(
        [
            {"type": "init", "goal_id": goal.goal_id},
            {"type": "answer", "step_id": "never-issued", "answer": "ответ"},
        ]
    )

    await goal_v2.goal_ws(socket)

    assert socket.sent[-1] == {"type": "error", "message": "Lesson step expired."}


@pytest.mark.asyncio
async def test_an_unusable_step_draft_reports_an_error_without_losing_the_goal(
    monkeypatch,
):
    class BrokenBuilder(RecordingStepBuilder):
        async def execute(self, goal, plan, *, previous_questions=()):
            raise ValueError("goal author returned incomplete step material")

    goal = replace(state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA)
    storage = FakeStorage(FakeSettings(), GoalRepository([goal]))
    install(
        monkeypatch,
        storage,
        checker=RecordingChecker(StepEvaluation("correct", "unclear", "ok")),
        builder=BrokenBuilder(),
    )
    socket = FakeWebSocket(
        [{"type": "init", "goal_id": goal.goal_id}, {"type": "next_step"}]
    )

    await goal_v2.goal_ws(socket)

    assert socket.sent[-1]["type"] == "error"
    assert storage.goals.find(goal.goal_id) is not None


def test_the_reminder_names_the_goal_that_still_needs_work():
    from api.settings import _goal_needing_review

    unframed = state_goal("Ещё без критериев", PROFILE)
    active = replace(
        state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA, last_worked_at=5.0
    )
    storage = FakeStorage(FakeSettings(), GoalRepository([unframed, active]))

    assert _goal_needing_review(storage) == "Понять Past Perfect"


def test_a_stored_goal_survives_a_round_trip_through_the_document():
    goal = replace(
        state_goal("Понять Past Perfect", PROFILE, material=GoalMaterial("Он ушёл.")),
        criteria=CRITERIA,
    )
    goal = RecordEvidence(GoalRoute()).execute(
        goal,
        GoalStep("s1", "c3", "compare_forms", "diagnose", MATERIAL, "Вопрос"),
        StepEvaluation("vague", "missed_signal", "Почти"),
        observed_at=42.0,
        answer="ответ",
        elapsed_seconds=25.0,
    )

    document = GoalRepository([goal]).to_document()
    restored = GoalRepository.from_document(document, PROFILE).find(goal.goal_id)

    assert restored == goal


def test_evidence_about_a_criterion_the_goal_no_longer_has_is_dropped():
    goal = replace(state_goal("Понять Past Perfect", PROFILE), criteria=CRITERIA[:1])
    document = GoalRepository([goal]).to_document()
    document[0]["evidence"] = [
        {
            "criterion_id": "c9",
            "activity": "compare_forms",
            "outcome": "correct",
            "cause": "unclear",
            "question": "Q",
            "answer": "A",
            "observed_at": 1.0,
        }
    ]

    restored = GoalRepository.from_document(document, PROFILE).find(goal.goal_id)

    assert restored.evidence == ()


def test_old_lesson_topics_become_goals_of_a_general_kind():
    document = [
        {"name": "Small talk", "blocks": [{"name": "Greetings"}], "last_reviewed": 7.0},
        {"name": "   ", "blocks": []},
    ]

    repository = GoalRepository.from_legacy_topics(document, PROFILE)

    assert [goal.statement for goal in repository.all()] == ["Small talk"]
    migrated = repository.all()[0]
    assert not migrated.framed
    assert migrated.last_worked_at == 7.0
    assert migrated.profile == PROFILE
