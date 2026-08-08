from __future__ import annotations

from dataclasses import replace

import pytest

from learning_core_v2.goal import (
    BuildGoalStep,
    CheckGoalAnswer,
    CloseGoal,
    CriterionDraft,
    DiscoveredPattern,
    DiscoveredTerm,
    Evidence,
    FrameGoal,
    GoalFraming,
    GoalMaterial,
    GoalReviewPolicy,
    GoalRoute,
    GoalStep,
    LearnerProfile,
    RecordEvidence,
    RoutePlan,
    StepDraft,
    StepEvaluation,
    StepMaterial,
    StepSection,
    SuccessCriterion,
    SummaryDraft,
    gaps,
    goal_achieved,
    goal_progress,
    progress_for,
    state_goal,
)


PROFILE = LearnerProfile("B1", "ru", "en", minutes=15)

CRITERIA = (
    SuccessCriterion("c1", "Recognize the form", 1),
    SuccessCriterion("c2", "Explain the sequence", 2),
    SuccessCriterion("c3", "Tell it apart from Past Simple", 3),
    SuccessCriterion("c4", "Use it in a new story", 4),
)

MATERIAL = StepMaterial(
    "Title", "Intro", (StepSection("Rule", text="Explanation"),)
)


class StubAuthor:
    def __init__(self) -> None:
        self.drafts = [
            CriterionDraft("  Recognize   the form ", 1),
            CriterionDraft("Explain the sequence", 2),
            CriterionDraft("Tell it apart", 3),
            CriterionDraft("Use it in a new story", 4),
        ]
        self.step_requests: list[object] = []
        self.evaluation = StepEvaluation("correct", "transfers_confidently", " Nice ")

    async def frame_goal(self, request):
        return GoalFraming(request.statement, tuple(self.drafts))

    async def write_step(self, request):
        self.step_requests.append(request)
        return StepDraft(
            StepMaterial(
                f" {request.criterion.statement} ",
                " Intro ",
                (StepSection(" Rule ", items=(" First ", ""), text=" Body "),),
            ),
            f"  Question about {request.activity}  ",
        )

    async def evaluate_step_answer(self, request):
        return self.evaluation

    async def write_goal_summary(self, request):
        return SummaryDraft(" You can now do it ", " Next goal ", ("  A  ", "A", ""))


class IDs:
    def __init__(self) -> None:
        self.count = 0

    def new(self) -> str:
        self.count += 1
        return f"step-{self.count}"


def a_goal(*, material: str = "", criteria=CRITERIA, evidence=(), **overrides):
    goal = state_goal(
        "Understand Past Perfect in stories",
        PROFILE,
        material=GoalMaterial(material),
        created_at=1.0,
    )
    return replace(goal, criteria=criteria, evidence=evidence, **overrides)


def answered(
    criterion_id: str,
    outcome: str,
    cause: str = "unclear",
    activity: str = "compare_forms",
) -> Evidence:
    return Evidence(criterion_id, activity, outcome, cause, "Q", "A", 10.0)


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def test_a_goal_must_be_stated_before_it_can_be_worked_on():
    with pytest.raises(ValueError):
        state_goal("   ", PROFILE)

    goal = state_goal("  Understand   Past Perfect ", PROFILE)
    assert goal.statement == "Understand Past Perfect"
    assert not goal.framed


def test_alphabet_course_does_not_collide_with_a_regular_goal():
    regular = state_goal("Learn the alphabet", PROFILE)
    course = state_goal("Learn the alphabet", PROFILE, kind="alphabet")

    assert regular.goal_id != course.goal_id
    assert course.kind == "alphabet"


@pytest.mark.asyncio
async def test_framing_turns_a_wish_into_ordered_checkable_criteria():
    goal = await FrameGoal(StubAuthor()).execute(state_goal("Learn Past Perfect", PROFILE))

    assert [item.criterion_id for item in goal.criteria] == ["c1", "c2", "c3", "c4"]
    assert goal.criteria[0].statement == "Recognize the form"
    assert [item.depth for item in goal.criteria] == [1, 2, 3, 4]
    assert goal.framed


@pytest.mark.asyncio
async def test_framing_keeps_a_production_criterion_at_the_top():
    author = StubAuthor()
    author.drafts = [CriterionDraft("Recognize it", 1), CriterionDraft("Explain it", 2)]

    goal = await FrameGoal(author).execute(state_goal("Learn Past Perfect", PROFILE))

    assert goal.criteria[-1].depth == 4
    assert goal.criteria[-1].required_demand == "productive"


@pytest.mark.asyncio
async def test_framing_rejects_duplicates_and_unusable_drafts():
    author = StubAuthor()
    author.drafts = [
        CriterionDraft("Recognize it", 1),
        CriterionDraft(" recognize   it ", 2),
        CriterionDraft("", 3),
    ]

    with pytest.raises(ValueError, match="no checkable criteria"):
        await FrameGoal(author).execute(state_goal("Learn Past Perfect", PROFILE))


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_the_first_step_probes_the_deepest_analytic_criterion():
    plan = GoalRoute().plan(a_goal())

    assert plan == RoutePlan("c3", "compare_forms", "diagnose")


def test_a_cleared_probe_skips_the_basics_it_implies():
    goal = a_goal(evidence=(answered("c3", "correct", "transfers_confidently"),))

    statuses = {item.criterion.criterion_id: item.status for item in goal_progress(goal)}
    assert statuses["c1"] == "implied"
    assert statuses["c2"] == "implied"

    # Nothing sends the learner back to recognizing the form.
    assert GoalRoute().plan(goal).criterion_id == "c3"


def test_a_failed_probe_drops_to_the_shallowest_untested_criterion():
    goal = a_goal(evidence=(answered("c3", "incorrect", "unknown_term"),))

    plan = GoalRoute().plan(goal)

    assert plan.criterion_id == "c1"
    assert plan.reason == "nearest_gap"


def test_the_route_repairs_the_cause_rather_than_repeating_the_question():
    causes = {
        "unknown_term": "explain_example",
        "rule_not_applied": "correct_error",
        "explains_not_produces": "create_example",
    }
    for cause, expected in causes.items():
        goal = a_goal(evidence=(answered("c3", "incorrect", cause, "predict_continuation"),))
        # c1 and c2 are untested, so aim the route at c3 directly.
        plan = GoalRoute()._advance(goal, progress_for(goal, CRITERIA[2]))
        assert plan == RoutePlan("c3", expected, "repair_cause")


def test_a_right_answer_the_learner_could_not_account_for_is_re_probed():
    goal = a_goal(evidence=(answered("c3", "correct", "lucky_guess", "compare_forms"),))

    plan = GoalRoute()._advance(goal, progress_for(goal, CRITERIA[2]))

    assert plan.reason == "repair_cause"
    # The same format would invite the same guess.
    assert plan.activity != "compare_forms"


def test_a_correct_receptive_answer_raises_the_demand():
    goal = a_goal(
        evidence=(answered("c4", "correct", "transfers_confidently", "explain_example"),)
    )

    plan = GoalRoute()._advance(goal, progress_for(goal, CRITERIA[3]))

    assert plan.reason == "raise_demand"
    assert plan.demand == "productive"


def test_find_in_material_is_never_planned_without_material():
    goal = a_goal(criteria=(SuccessCriterion("c1", "Spot the form", 1),))

    plan = GoalRoute().plan(goal)

    assert plan.activity == "explain_example"
    assert GoalRoute().plan(a_goal(criteria=goal.criteria, material="A story")).activity == (
        "find_in_material"
    )


def test_a_repair_never_repeats_the_activity_that_just_failed():
    """With no material the receptive tier holds one usable activity only."""
    goal = a_goal(
        criteria=(SuccessCriterion("c1", "Spot the form", 1),),
        evidence=(answered("c1", "incorrect", "missed_signal", "explain_example"),),
    )

    plan = GoalRoute().plan(goal)

    assert plan.activity != "explain_example"
    # Repairing may step up a tier, but never down to something easier.
    assert plan.demand != "receptive"


def test_the_last_question_is_an_unaided_application():
    proof = tuple(
        answered("c4", "correct", "transfers_confidently", activity)
        for activity in ("create_example", "role_reply")
    )
    goal = a_goal(evidence=proof)

    plan = GoalRoute().plan(goal)

    assert plan == RoutePlan("c4", "apply_unaided", "final_check")
    assert not goal_achieved(goal)


def test_alphabet_course_checks_handwriting_and_keyboard_before_final_reading():
    writing_profile = LearnerProfile(
        "A1", "ru", "th", writing_support="new_alphabet", script_name="Thai script"
    )
    proof = tuple(
        answered("c4", "correct", "transfers_confidently", activity)
        for activity in ("create_example", "role_reply")
    )
    goal = a_goal(evidence=proof, kind="alphabet", profile=writing_profile)

    handwriting = GoalRoute().plan(goal)
    assert handwriting == RoutePlan("c4", "handwrite_form", "consolidate")

    goal = replace(
        goal,
        evidence=(*goal.evidence, answered("c4", "correct", "unclear", "handwrite_form")),
    )
    keyboard = GoalRoute().plan(goal)
    assert keyboard == RoutePlan("c4", "type_on_keyboard", "consolidate")

    goal = replace(
        goal,
        evidence=(*goal.evidence, answered("c4", "correct", "unclear", "type_on_keyboard")),
    )
    assert GoalRoute().plan(goal) == RoutePlan("c4", "apply_unaided", "final_check")


def test_the_goal_closes_only_after_an_unaided_success():
    goal = a_goal(
        evidence=(
            answered("c4", "correct", "transfers_confidently", "create_example"),
            answered("c4", "correct", "transfers_confidently", "apply_unaided"),
        )
    )

    assert goal_achieved(goal)
    assert GoalRoute().plan(goal) is None


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_one_answer_never_settles_a_criterion():
    goal = a_goal(evidence=(answered("c4", "correct", "transfers_confidently", "create_example"),))

    progress = progress_for(goal, CRITERIA[3])

    assert progress.attempts == 1
    assert progress.status == "emerging"


def test_a_guess_moves_a_criterion_far_less_than_understanding():
    reasoned = a_goal(
        evidence=tuple(
            answered("c3", "correct", "transfers_confidently") for _ in range(2)
        )
    )
    guessed = a_goal(
        evidence=tuple(answered("c3", "correct", "lucky_guess") for _ in range(2))
    )

    assert progress_for(reasoned, CRITERIA[2]).status == "met"
    assert progress_for(guessed, CRITERIA[2]).status != "met"
    assert (
        progress_for(guessed, CRITERIA[2]).confidence
        < progress_for(reasoned, CRITERIA[2]).confidence
    )


def test_explaining_without_producing_does_not_meet_a_production_criterion():
    goal = a_goal(
        evidence=tuple(
            answered("c4", "correct", "transfers_confidently", "explain_example")
            for _ in range(3)
        )
    )

    progress = progress_for(goal, CRITERIA[3])

    assert progress.confidence > 0.75
    assert progress.status == "emerging"


def test_gaps_list_the_remaining_criteria_shallowest_first():
    goal = a_goal(evidence=(answered("c2", "incorrect", "missed_signal"),))

    listed = gaps(goal)

    assert [item.criterion_id for item in listed] == ["c1", "c2", "c3", "c4"]
    assert listed[1].status == "gap"
    assert listed[1].cause == "missed_signal"


@pytest.mark.asyncio
async def test_recording_appends_evidence_and_replans_from_it():
    goal = a_goal()
    step = GoalStep("step-1", "c3", "compare_forms", "diagnose", MATERIAL, "Which one?")
    recorder = RecordEvidence(GoalRoute())

    updated = recorder.execute(
        goal,
        step,
        StepEvaluation(
            "correct",
            "transfers_confidently",
            "Good",
            terms=(DiscoveredTerm("had left", "уже ушёл"),),
            patterns=(
                DiscoveredPattern("tense_aspect", "Past Perfect", "Earlier past", "had left"),
            ),
        ),
        observed_at=100.0,
        answer="  the   first one ",
        elapsed_seconds=30.0,
    )

    assert updated.evidence[-1].answer == "the first one"
    assert updated.evidence[-1].criterion_id == "c3"
    assert updated.spent_seconds == 30.0
    assert updated.last_worked_at == 100.0
    assert updated.terms[0].term == "had left"
    assert updated.patterns[0].label == "Past Perfect"
    assert updated.next_plan is not None and updated.next_plan.criterion_id == "c3"


def test_off_task_input_is_answered_again_rather_than_recorded():
    goal = a_goal()
    step = GoalStep("step-1", "c3", "compare_forms", "diagnose", MATERIAL, "Which one?")

    unchanged = RecordEvidence(GoalRoute()).execute(
        goal,
        step,
        StepEvaluation("garbage", "unclear", "Please answer the question."),
        observed_at=100.0,
        elapsed_seconds=30.0,
    )

    assert unchanged is goal


# ---------------------------------------------------------------------------
# Steps and answers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_step_is_normalized_and_carries_a_server_identifier():
    goal = a_goal(material="Once he had left, the room went quiet.")
    author = StubAuthor()

    step = await BuildGoalStep(author, IDs()).execute(
        goal, RoutePlan("c2", "explain_example", "nearest_gap"), previous_questions=["Old"]
    )

    assert step.step_id == "step-1"
    assert step.question == "Question about explain_example"
    assert step.material.sections[0].items == ("First",)
    request = author.step_requests[0]
    assert request.previous_questions == ("Old",)
    assert request.observed_gaps[0].criterion_id == "c1"


@pytest.mark.asyncio
async def test_an_empty_answer_is_not_sent_to_the_author():
    class Unreachable(StubAuthor):
        async def evaluate_step_answer(self, request):
            raise AssertionError("empty answers must not reach the author")

    goal = a_goal()
    step = GoalStep("step-1", "c3", "compare_forms", "diagnose", MATERIAL, "Which one?")

    result = await CheckGoalAnswer(Unreachable()).execute(goal, step, "   ")

    assert result.outcome == "garbage"
    assert not result.should_record


@pytest.mark.asyncio
async def test_an_unknown_difficulty_cause_is_rejected():
    author = StubAuthor()
    author.evaluation = StepEvaluation("correct", "vibes", "Good")  # type: ignore[arg-type]
    goal = a_goal()
    step = GoalStep("step-1", "c3", "compare_forms", "diagnose", MATERIAL, "Which one?")

    with pytest.raises(ValueError, match="invalid difficulty cause"):
        await CheckGoalAnswer(author).execute(goal, step, "an answer")


@pytest.mark.asyncio
async def test_incomplete_step_material_is_rejected():
    class Incomplete(StubAuthor):
        async def write_step(self, request):
            return StepDraft(StepMaterial("", "", ()), "A question")

    with pytest.raises(ValueError, match="incomplete step material"):
        await BuildGoalStep(Incomplete(), IDs()).execute(
            a_goal(), RoutePlan("c1", "explain_example", "diagnose")
        )


# ---------------------------------------------------------------------------
# Closing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_report_separates_what_is_proven_from_what_is_shaky():
    goal = a_goal(
        evidence=(
            answered("c4", "correct", "transfers_confidently", "create_example"),
            answered("c4", "correct", "transfers_confidently", "apply_unaided"),
        )
    )

    report = await CloseGoal(StubAuthor()).execute(goal)

    assert report.achieved
    assert not report.stopped_on_time
    assert [item.criterion.criterion_id for item in report.proven] == ["c1", "c2", "c3", "c4"]
    assert report.shaky == ()
    assert report.narrative == "You can now do it"
    assert report.next_goal == "Next goal"
    assert report.examples == ("A",)


@pytest.mark.asyncio
async def test_a_goal_stopped_by_the_clock_reports_what_is_still_unstable():
    goal = a_goal(
        evidence=(answered("c1", "incorrect", "unknown_term"),),
        spent_seconds=PROFILE.minutes * 60.0,
    )

    report = await CloseGoal(StubAuthor()).execute(goal)

    assert not report.achieved
    assert report.stopped_on_time
    assert [item.criterion.criterion_id for item in report.shaky] == ["c1", "c2", "c3", "c4"]


def test_the_reminder_points_at_the_goal_left_alone_longest():
    unframed = state_goal("No criteria yet", PROFILE)
    stale = a_goal(evidence=(answered("c1", "incorrect", "unknown_term"),))
    finished = a_goal(
        evidence=(
            answered("c4", "correct", "transfers_confidently", "create_example"),
            answered("c4", "correct", "transfers_confidently", "apply_unaided"),
        )
    )

    policy = GoalReviewPolicy()

    assert policy.first_due([unframed, finished, stale]) == stale.statement
    assert policy.first_due([unframed, finished]) is None
