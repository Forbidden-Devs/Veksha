from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from learning_core_v2.acquisition import (
    LexicalItem,
    ReviewSchedule,
    VocabularyEncounter,
)
from learning_core_v2.practice import (
    MAX_CORRECTION_STEPS,
    AnswerCheckRequest,
    AnswerEvaluation,
    BuildPracticeTask,
    CheckPracticeAnswer,
    LearnerCapabilities,
    PlanReason,
    PracticePlan,
    PracticePlanner,
    PracticeQueue,
    PracticeSession,
    PracticeTask,
    SKILL_FORMATS,
    TASK_SKILL,
    TaskDraft,
    aggregate_skills,
    suggest_rating,
)
from learning_core_v2.skills import SkillProfile, SkillState, record_attempt


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
    draft: TaskDraft = field(default_factory=lambda: TaskDraft("Translate this"))
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
    schedule_fields = {
        key: overrides.pop(key)
        for key in tuple(overrides)
        if key in {"review_count", "next_review_at", "added_at"}
    }
    status = "known" if overrides.pop("known", False) else "learning"
    context = overrides.pop("context", "")
    return LexicalItem(
        item_id=f"item-{text.casefold()}",
        term=text,
        language=overrides.pop("language", "en"),
        translation=overrides.pop("translation", ""),
        status=status,
        encounters=((VocabularyEncounter(context=context),) if context else ()),
        schedule=ReviewSchedule(**schedule_fields),
        **overrides,
    )


def profile(**confidences) -> SkillProfile:
    result = SkillProfile()
    for skill, confidence in confidences.items():
        result = result.with_state(
            skill, SkillState(attempts=3, streak=2, confidence=confidence)
        )
    return result


def planner(**kwargs) -> PracticePlanner:
    return PracticePlanner(PracticeQueue(kwargs.pop("horizon", 100)), FirstChoice())


def plan_one(items, *, now=1_000, capabilities=None, memory=None, **kwargs):
    from learning_core_v2.practice import SessionMemory

    return planner(**kwargs).plan(
        items,
        learning_language="en",
        now=now,
        memory=memory or SessionMemory(),
        capabilities=capabilities or LearnerCapabilities(),
    )


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


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

    assert [item.term for item in available] == [
        "earlier",
        "later",
        "newer-first",
        "newer",
    ]


def test_queue_honors_stable_item_id_exclusions():
    queue = PracticeQueue(review_horizon_seconds=0)
    available = queue.available(
        [word("Run"), word("Walk")],
        learning_language="en",
        now=1_000,
        excluded={"item-run"},
    )

    assert [item.term for item in available] == ["Walk"]


# --------------------------------------------------------------------------
# Planning: skill selection
# --------------------------------------------------------------------------


def test_planner_trains_the_weakest_skill_not_a_random_format():
    item = replace(
        word("come across", translation="натыкаться", review_count=2),
        skills=profile(recognition=0.95, recall=0.2, contextual_meaning=0.8),
    )

    plan = plan_one([item])

    assert plan is not None
    assert plan.skill == "recall"
    assert plan.kind in SKILL_FORMATS["recall"].core
    assert plan.reason.code == "weakest_skill"


def test_planner_skips_formats_the_material_cannot_support():
    # No saved translation and no observed sentence: only skills whose core
    # formats need neither resource can be planned.
    plan = plan_one([word("run", review_count=2)])

    assert plan is not None
    assert plan.skill in {"recognition", "contextual_meaning"}
    assert plan.kind in {"translation", "synonym", "usage_example"}


def test_planner_omits_listening_until_the_client_can_speak():
    item = replace(
        word("run", translation="бежать", context="He runs fast.", review_count=2),
        skills=profile(
            recognition=0.9, recall=0.9, contextual_meaning=0.9, listening=0.05
        ),
    )

    silent = plan_one([item])
    speaking = plan_one([item], capabilities=LearnerCapabilities(audio=True))

    assert silent is not None and silent.skill != "listening"
    assert speaking is not None and speaking.skill == "listening"


def test_planner_reports_a_recent_error_as_the_reason():
    item = replace(
        word("run", translation="бежать", review_count=2),
        skills=SkillProfile().with_state(
            "recall", SkillState(attempts=2, errors=1, streak=0, confidence=0.3)
        ),
    )

    plan = plan_one([item])

    assert plan is not None
    assert plan.reason == PlanReason("recent_error", "recall")


def test_planner_prefers_the_overdue_sense_between_equal_skills():
    stale = word("stale", translation="a", review_count=2, next_review_at=100)
    fresh = word("fresh", translation="b", review_count=2, next_review_at=1_000)

    plan = plan_one([fresh, stale], now=1_000)

    assert plan is not None
    assert plan.item.term == "stale"


def test_planner_spreads_formats_across_a_session():
    from learning_core_v2.practice import SessionMemory

    items = [
        replace(
            word(f"w{index}", translation="x", review_count=2),
            skills=profile(recognition=0.2),
        )
        for index in range(4)
    ]
    memory = SessionMemory()
    engine = planner()

    kinds = []
    for _ in range(3):
        plan = engine.plan(
            items,
            learning_language="en",
            now=1_000,
            memory=memory,
            capabilities=LearnerCapabilities(),
        )
        assert plan is not None
        kinds.append(plan.kind)
        memory.record(plan)

    # No format is asked twice in a row once another one is equally rested.
    assert all(first != second for first, second in zip(kinds, kinds[1:]))


# --------------------------------------------------------------------------
# Task building
# --------------------------------------------------------------------------


def build(kind, draft, item=None):
    provider = StubProvider(draft=draft)
    service = BuildPracticeTask(provider, FixedIdentifiers())
    plan = PracticePlan(
        item=item or word("run", translation="бежать", context="He runs."),
        skill=TASK_SKILL[kind],
        kind=kind,
        reason=PlanReason("due_review", TASK_SKILL[kind]),
    )
    return service, plan, provider


@pytest.mark.asyncio
async def test_task_builder_passes_the_planned_skill_to_the_provider():
    service, plan, provider = build(
        "reverse_translation", TaskDraft("Как сказать «бежать»?", "run")
    )

    task = await service.execute(
        plan, proficiency="b1", native_language="ru", learning_language="en"
    )

    assert task.kind == "reverse_translation"
    assert task.skill == "recall"
    assert task.expected_answer == "run"
    assert provider.draft_requests[0].skill == "recall"


@pytest.mark.asyncio
async def test_choice_task_requires_options_that_contain_the_answer():
    service, plan, _ = build(
        "multiple_choice",
        TaskDraft("Что значит слово?", "бежать", options=("идти", "плыть", "лететь")),
    )

    with pytest.raises(ValueError):
        await service.execute(
            plan, proficiency="b1", native_language="ru", learning_language="en"
        )


@pytest.mark.asyncio
async def test_listening_task_requires_something_to_voice():
    service, plan, _ = build("listening_recall", TaskDraft("Запишите услышанное", "run"))

    with pytest.raises(ValueError):
        await service.execute(
            plan, proficiency="b1", native_language="ru", learning_language="en"
        )


@pytest.mark.asyncio
async def test_non_choice_task_drops_stray_options_and_audio():
    service, plan, _ = build(
        "translation",
        TaskDraft("Что значит run?", "бежать", options=("a", "b"), audio_text="run"),
    )

    task = await service.execute(
        plan, proficiency="b1", native_language="ru", learning_language="en"
    )

    assert task.options == ()
    assert task.audio_text == ""


@pytest.mark.asyncio
async def test_blank_answer_is_garbage_without_provider_call():
    provider = StubProvider()
    checker = CheckPracticeAnswer(provider)
    task = PracticeTask(
        "task-id",
        "item-run",
        "run",
        "",
        "translation",
        "recognition",
        "core",
        "Question",
        -1,
        PlanReason("due_review", "recognition"),
    )

    result = await checker.execute(AnswerCheckRequest(task, "  ", "b1", "ru", "en"))

    assert result.outcome == "garbage"
    assert result.is_answer is False
    assert provider.check_requests == []


# --------------------------------------------------------------------------
# Grading across all four FSRS ratings
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "seconds", "hints", "corrected", "expected"),
    [
        ("incorrect", 5.0, 0, False, "again"),
        ("vague", 5.0, 0, False, "hard"),
        ("correct", 3.0, 0, False, "easy"),
        ("correct", 20.0, 0, False, "good"),
        ("correct", 90.0, 0, False, "hard"),
        ("correct", 3.0, 1, False, "hard"),
        ("correct", 3.0, 0, True, "hard"),
        ("correct", 0.0, 0, False, "good"),
        ("garbage", 3.0, 0, False, None),
    ],
)
def test_rating_combines_verdict_time_hints_and_repairs(
    outcome, seconds, hints, corrected, expected
):
    assert (
        suggest_rating(
            "translation",
            outcome,
            response_seconds=seconds,
            hints_used=hints,
            corrected=corrected,
        )
        == expected
    )


def test_choice_tasks_get_a_tighter_fast_window_than_written_ones():
    # Ten seconds is fast for a written answer, slow for picking an option.
    assert suggest_rating("translation", "correct", response_seconds=10.0) == "good"
    assert suggest_rating("multiple_choice", "correct", response_seconds=3.0) == "easy"
    assert suggest_rating("multiple_choice", "correct", response_seconds=10.0) == "good"


def test_skill_confidence_moves_with_the_rating():
    state = SkillState()
    good = record_attempt(state, "good", now=10)
    again = record_attempt(state, "again", now=10)

    assert good.confidence > state.confidence
    assert again.confidence < state.confidence
    assert again.streak == 0 and again.errors == 1
    assert good.streak == 1


# --------------------------------------------------------------------------
# Session: the corrective chain
# --------------------------------------------------------------------------


def session(items, *, target=5, audio=False):
    return PracticeSession(
        planner(),
        target_tasks=target,
        capabilities=LearnerCapabilities(audio=audio),
        learning_language="en",
    )


def task_for(plan, task_id="task", question="Q", expected="run"):
    return PracticeTask(
        task_id=task_id,
        item_id=plan.item.item_id,
        word=plan.item.term,
        context=plan.item.latest_context,
        kind=plan.kind,
        skill=plan.skill,
        stage=plan.stage,
        question=question,
        review_count=plan.item.schedule.review_count,
        reason=plan.reason,
        expected_answer=expected,
    )


def run_task(active, items, *, rating_outcome, task_id, now=1_000):
    plan = active.plan_next(items, now=now)
    assert plan is not None
    task = task_for(plan, task_id=task_id)
    active.register(plan, task)
    graded = active.grade(
        task,
        AnswerEvaluation(rating_outcome, "feedback"),
        now=now,
        response_seconds=20.0,
    )
    return plan, graded


def test_error_opens_a_support_step_then_a_transfer_check():
    items = [
        replace(
            word("run", translation="бежать", context="He runs.", review_count=2),
            skills=profile(recall=0.1),
        )
    ]
    active = session(items)

    first, graded = run_task(active, items, rating_outcome="incorrect", task_id="t1")
    assert graded.rating == "again"
    assert graded.correction is not None
    assert graded.correction.stage == "support"

    support_plan = active.plan_next(items, now=1_000)
    assert support_plan is not None
    assert support_plan.stage == "support"
    assert support_plan.skill == first.skill
    assert support_plan.kind == SKILL_FORMATS[first.skill].support
    assert support_plan.reason.code == "correction_support"

    support = task_for(support_plan, task_id="t2")
    active.register(support_plan, support)
    support_graded = active.grade(
        support, AnswerEvaluation("correct", "ok"), now=1_000, response_seconds=20.0
    )
    assert support_graded.correction is not None
    assert support_graded.correction.stage == "transfer"

    transfer_plan = active.plan_next(items, now=1_000)
    assert transfer_plan is not None
    assert transfer_plan.stage == "transfer"
    assert transfer_plan.kind in SKILL_FORMATS[first.skill].core
    assert transfer_plan.kind != first.kind


def test_corrective_tasks_do_not_reschedule_the_sense():
    items = [word("run", translation="бежать", review_count=2)]
    active = session(items)

    _, graded = run_task(active, items, rating_outcome="incorrect", task_id="t1")
    assert graded.counts_as_review is True

    support_plan = active.plan_next(items, now=1_000)
    support = task_for(support_plan, task_id="t2")
    active.register(support_plan, support)
    support_graded = active.grade(
        support, AnswerEvaluation("correct", "ok"), now=1_000, response_seconds=5.0
    )

    # The repair moves the skill, not FSRS: one lapse must not reschedule twice.
    assert support_graded.counts_as_review is False
    assert support_graded.rating is not None
    assert active.reviewed == 1


def test_a_failed_support_task_ends_the_chain():
    items = [word("run", translation="бежать", review_count=2)]
    active = session(items)

    run_task(active, items, rating_outcome="incorrect", task_id="t1")
    support_plan = active.plan_next(items, now=1_000)
    support = task_for(support_plan, task_id="t2")
    active.register(support_plan, support)
    graded = active.grade(
        support, AnswerEvaluation("incorrect", "no"), now=1_000, response_seconds=5.0
    )

    assert graded.correction is None


def test_correction_chain_is_bounded_per_sense():
    items = [word("run", translation="бежать", context="He runs.", review_count=2)]
    active = session(items)

    run_task(active, items, rating_outcome="incorrect", task_id="t1")
    repairs = 0
    for index in range(6):
        plan = active.plan_next(items, now=1_000)
        if plan is None or plan.stage == "core":
            break
        repairs += 1
        task = task_for(plan, task_id=f"r{index}")
        active.register(plan, task)
        active.grade(
            task, AnswerEvaluation("correct", "ok"), now=1_000, response_seconds=5.0
        )

    assert repairs == MAX_CORRECTION_STEPS


def test_manual_rating_overrides_the_suggestion():
    items = [word("run", translation="бежать", review_count=2)]
    active = session(items)
    plan = active.plan_next(items, now=1_000)
    task = task_for(plan, task_id="t1")
    active.register(plan, task)

    graded = active.grade(
        task,
        AnswerEvaluation("correct", "ok"),
        now=1_000,
        response_seconds=20.0,
        requested_rating="easy",
    )

    assert graded.suggested_rating == "good"
    assert graded.rating == "easy"
    assert graded.manual_rating is True


def test_a_non_answer_leaves_the_task_open_for_a_retry():
    items = [word("run", translation="бежать", review_count=2)]
    active = session(items)
    plan = active.plan_next(items, now=1_000)
    task = task_for(plan, task_id="t1")
    active.register(plan, task)

    graded = active.grade(task, AnswerEvaluation("garbage", "?"), now=1_000)

    assert graded.rating is None
    assert graded.counts_as_review is False
    assert active.task("t1") is task


def test_session_stops_planning_at_the_target_but_still_repairs():
    items = [
        word(f"w{index}", translation="x", review_count=2, next_review_at=index)
        for index in range(4)
    ]
    active = session(items, target=2)

    run_task(active, items, rating_outcome="correct", task_id="t1")
    run_task(active, items, rating_outcome="incorrect", task_id="t2")

    repair = active.plan_next(items, now=1_000)
    assert repair is not None and repair.stage == "support"

    task = task_for(repair, task_id="t3")
    active.register(repair, task)
    active.grade(task, AnswerEvaluation("incorrect", "no"), now=1_000)

    assert active.plan_next(items, now=1_000) is None


def test_summary_names_the_skill_still_limiting_each_sense():
    items = [
        replace(
            word("run", translation="бежать", review_count=2),
            skills=profile(recognition=0.9, recall=0.2),
        )
    ]
    active = session(items)
    plan = active.plan_next(items, now=1_000)
    task = task_for(plan, task_id="t1")
    active.register(plan, task)
    active.grade(
        task, AnswerEvaluation("correct", "ok"), now=1_000, response_seconds=20.0
    )

    summary = active.summary()

    assert summary.reviewed == 1
    assert len(summary.items) == 1
    report = summary.items[0]
    assert report.term == "run"
    assert report.consolidated is True
    assert report.limiting_skill == "recall"


def test_summary_marks_a_sense_left_unresolved():
    items = [word("run", translation="бежать", review_count=2)]
    active = session(items)

    run_task(active, items, rating_outcome="incorrect", task_id="t1")
    support = active.plan_next(items, now=1_000)
    task = task_for(support, task_id="t2")
    active.register(support, task)
    active.grade(task, AnswerEvaluation("incorrect", "no"), now=1_000)

    assert active.summary().items[0].consolidated is False


def test_marking_a_sense_known_drops_it_and_its_pending_repairs():
    items = [word("run", translation="бежать", review_count=2)]
    active = session(items)

    run_task(active, items, rating_outcome="incorrect", task_id="t1")
    active.drop_item("item-run")

    assert active.plan_next(items, now=1_000) is None


# --------------------------------------------------------------------------
# Legacy data
# --------------------------------------------------------------------------


def test_senses_without_a_skill_profile_start_neutral():
    legacy = word("run", translation="бежать", review_count=2)

    reports = {report.skill: report for report in aggregate_skills([legacy])}

    assert all(report.attempts == 0 for report in reports.values())
    assert all(report.confidence == pytest.approx(0.5) for report in reports.values())
    # A neutral profile is plannable, and is not treated as a failure.
    plan = plan_one([legacy])
    assert plan is not None
    assert plan.reason.code != "recent_error"
