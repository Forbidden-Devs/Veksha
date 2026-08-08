"""Goal-oriented lessons: a checkable outcome, an adaptive route, evidence.

A lesson no longer starts from a topic that is sliced into a fixed list of
blocks. It starts from a result the learner wants — "understand Past Perfect
in stories", "get ready for the client call", "work through this article" —
and the route to that result is recomputed after every answer.

Three ideas carry the module:

*Checkable criteria.* A wish like "learn Past Perfect" is useless as a stop
condition. :class:`FrameGoal` turns it into ordered criteria the learner can
demonstrably meet — recognize the form, explain the sequence, tell it apart
from Past Simple, use it in a fresh story — each with a demand level.

*Evidence, not verdicts.* One answer never settles a criterion. Every answer
is stored as :class:`Evidence` carrying both the outcome and *why* it went
that way (:data:`DifficultyCause`), and status is derived from the whole run.
A right answer the learner admits was a guess moves the criterion far less
than one they could explain.

*Routing from the last answer.* :class:`GoalRoute` is pure: given the goal and
its evidence it names the next criterion, the next kind of activity, and the
reason. A learner who already handles the form is never walked back through
basic theory; a learner who picks the right tense but cannot say why gets a
question aimed at exactly that.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol


Outcome = Literal["correct", "vague", "incorrect", "garbage"]
GoalKind = Literal["standard", "alphabet"]

#: Why an answer came out the way it did. The route repairs the *cause*, so a
#: learner who knows the rule but forgets to apply it is not re-taught the rule.
DifficultyCause = Literal[
    "unknown_term",           # a word or term in the task was not understood
    "missed_signal",          # the cue was there in the material and went unseen
    "rule_not_applied",       # can state the rule, did not use it here
    "lucky_guess",            # right answer, no reasoning behind it
    "explains_not_produces",  # can describe it, cannot yet build it
    "transfers_confidently",  # carried it into a situation the lesson never showed
    "unclear",                # the answer does not reveal a cause
]

#: What the lesson asks the learner to *do* next. The list is deliberately
#: wider than "read then answer": a goal is reached through varied action.
ActivityKind = Literal[
    "find_in_material",       # locate the phenomenon in the learner's own source
    "explain_example",        # one worked example, then the same move on a second
    "compare_forms",          # tell two constructions apart
    "correct_error",          # repair a wrong sentence
    "predict_continuation",   # say what must come next and why
    "paraphrase",             # restate in the learner's own words
    "create_example",         # build a fresh example unaided by a template
    "role_reply",             # answer in role, inside the goal's situation
    "handwrite_form",         # form symbols by hand and check their structure
    "type_on_keyboard",       # locate and type symbols with the target layout
    "apply_unaided",          # final application with no scaffolding at all
]

#: How much the learner has to generate. A criterion is only met once it has a
#: correct answer at (or above) the demand its depth calls for — recognizing a
#: form in a multiple-choice frame never proves you can write with it.
Demand = Literal["receptive", "analytic", "productive"]

CriterionStatus = Literal["untested", "gap", "emerging", "implied", "met"]

RouteReason = Literal[
    "diagnose",
    "nearest_gap",
    "repair_cause",
    "raise_demand",
    "consolidate",
    "final_check",
]

CAUSES: tuple[DifficultyCause, ...] = (
    "unknown_term",
    "missed_signal",
    "rule_not_applied",
    "lucky_guess",
    "explains_not_produces",
    "transfers_confidently",
    "unclear",
)

ACTIVITY_DEMAND: dict[ActivityKind, Demand] = {
    "find_in_material": "receptive",
    "explain_example": "receptive",
    "compare_forms": "analytic",
    "correct_error": "analytic",
    "predict_continuation": "analytic",
    "paraphrase": "analytic",
    "create_example": "productive",
    "role_reply": "productive",
    "handwrite_form": "productive",
    "type_on_keyboard": "productive",
    "apply_unaided": "productive",
}

ACTIVITIES: tuple[ActivityKind, ...] = tuple(ACTIVITY_DEMAND)

_DEMAND_RANK: dict[Demand, int] = {"receptive": 0, "analytic": 1, "productive": 2}

#: Ordered fallbacks per demand tier, so "same activity twice in a row" can
#: always be avoided without dropping to a weaker kind of practice.
_BY_DEMAND: dict[Demand, tuple[ActivityKind, ...]] = {
    "receptive": ("find_in_material", "explain_example"),
    "analytic": ("compare_forms", "correct_error", "predict_continuation", "paraphrase"),
    "productive": (
        "create_example",
        "role_reply",
        "handwrite_form",
        "type_on_keyboard",
        "apply_unaided",
    ),
}

#: Where to look next when a tier runs out of unused activities: sideways
#: first, then up. Never down — a repair must not become easier than the task
#: that was just failed.
_ESCALATION: dict[Demand, tuple[Demand, ...]] = {
    "receptive": ("receptive", "analytic"),
    "analytic": ("analytic", "productive"),
    "productive": ("productive", "analytic"),
}

#: Criterion depth, 1..4: recognize the form, explain it, tell it apart, use it.
MIN_DEPTH = 1
MAX_DEPTH = 4

_DEPTH_DEMAND: dict[int, Demand] = {
    1: "receptive",
    2: "analytic",
    3: "analytic",
    4: "productive",
}

_DEPTH_PROBE: dict[int, ActivityKind] = {
    1: "find_in_material",
    2: "explain_example",
    3: "compare_forms",
    4: "create_example",
}

#: The activity that repairs each cause. Repairing the cause rather than
#: repeating the question is the whole point of storing causes at all.
_REPAIR: dict[DifficultyCause, ActivityKind] = {
    "unknown_term": "explain_example",
    "missed_signal": "find_in_material",
    "rule_not_applied": "correct_error",
    "lucky_guess": "compare_forms",
    "explains_not_produces": "create_example",
    "transfers_confidently": "apply_unaided",
    "unclear": "explain_example",
}

_OUTCOME_VALUE: dict[Outcome, float] = {
    "correct": 1.0,
    "vague": 0.5,
    "incorrect": 0.0,
    "garbage": 0.0,
}

#: A right answer the learner cannot account for is worth barely more than a
#: coin flip; a confident transfer is worth full marks.
_CAUSE_CEILING: dict[DifficultyCause, float] = {
    "lucky_guess": 0.45,
    "explains_not_produces": 0.6,
}

_NEUTRAL_CONFIDENCE = 0.5
_LEARNING_RATE = 0.45
_MET_CONFIDENCE = 0.75
_GAP_CONFIDENCE = 0.4
_MIN_ATTEMPTS_TO_MEET = 2

_GOAL_NAMESPACE = uuid.UUID("8f2a5f2e-6d1c-4d0e-9f4a-5c1b0f6d3a77")

MAX_CRITERIA = 6
MAX_EVIDENCE = 120
DEFAULT_MINUTES = 15


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    """The constraints a goal has to be reached inside."""

    proficiency: str
    native_language: str
    learning_language: str
    minutes: int = DEFAULT_MINUTES
    writing_support: str = "standard"
    script_name: str = ""
    transcription_mode: str = "standard"

    def __post_init__(self) -> None:
        if self.minutes < 1:
            raise ValueError("goal duration must be at least one minute")


@dataclass(frozen=True, slots=True)
class GoalMaterial:
    """The article, message or situation the goal is anchored to, if any."""

    text: str = ""
    source_url: str = ""

    @property
    def present(self) -> bool:
        return bool(self.text.strip())


@dataclass(frozen=True, slots=True)
class SuccessCriterion:
    """One checkable part of the goal."""

    criterion_id: str
    statement: str
    depth: int

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("criterion needs an identifier")
        if not self.statement.strip():
            raise ValueError("criterion needs a statement")
        if not MIN_DEPTH <= self.depth <= MAX_DEPTH:
            raise ValueError("criterion depth must be between one and four")

    @property
    def required_demand(self) -> Demand:
        return _DEPTH_DEMAND[self.depth]


@dataclass(frozen=True, slots=True)
class Evidence:
    """One observed answer, kept as an observation rather than a grade."""

    criterion_id: str
    activity: ActivityKind
    outcome: Outcome
    cause: DifficultyCause
    question: str
    answer: str
    observed_at: float = 0.0

    @property
    def demand(self) -> Demand:
        return ACTIVITY_DEMAND[self.activity]

    @property
    def counts(self) -> bool:
        """Off-task input is not evidence about the learner's knowledge."""
        return self.outcome != "garbage"

    @property
    def value(self) -> float:
        score = _OUTCOME_VALUE[self.outcome]
        ceiling = _CAUSE_CEILING.get(self.cause)
        return min(score, ceiling) if ceiling is not None else score


@dataclass(frozen=True, slots=True)
class DiscoveredTerm:
    """A word the lesson surfaced, on its way to the Vocabulary Inbox."""

    term: str
    translation: str
    context: str = ""


@dataclass(frozen=True, slots=True)
class DiscoveredPattern:
    """A construction the lesson surfaced, on its way to Pattern Workshop."""

    category: str
    label: str
    explanation: str
    example: str


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """The next step, decided before any model is asked to write it."""

    criterion_id: str
    activity: ActivityKind
    reason: RouteReason

    @property
    def demand(self) -> Demand:
        return ACTIVITY_DEMAND[self.activity]


@dataclass(frozen=True, slots=True)
class LearningGoal:
    """A goal, its criteria, and everything observed on the way to it."""

    goal_id: str
    statement: str
    profile: LearnerProfile
    kind: GoalKind = "standard"
    material: GoalMaterial = GoalMaterial()
    criteria: tuple[SuccessCriterion, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    next_plan: RoutePlan | None = None
    terms: tuple[DiscoveredTerm, ...] = ()
    patterns: tuple[DiscoveredPattern, ...] = ()
    spent_seconds: float = 0.0
    created_at: float = 0.0
    last_worked_at: float | None = None
    achieved_at: float | None = None

    @property
    def framed(self) -> bool:
        """False until diagnosis has produced criteria to work against."""
        return bool(self.criteria)

    @property
    def budget_seconds(self) -> float:
        return float(self.profile.minutes) * 60.0

    def criterion(self, criterion_id: str) -> SuccessCriterion | None:
        return next(
            (item for item in self.criteria if item.criterion_id == criterion_id),
            None,
        )

    def evidence_for(self, criterion_id: str) -> tuple[Evidence, ...]:
        return tuple(
            item
            for item in self.evidence
            if item.criterion_id == criterion_id and item.counts
        )

    @property
    def deepest(self) -> SuccessCriterion | None:
        if not self.criteria:
            return None
        return max(self.criteria, key=lambda item: item.depth)


@dataclass(frozen=True, slots=True)
class CriterionProgress:
    """What the accumulated evidence says about one criterion."""

    criterion: SuccessCriterion
    status: CriterionStatus
    confidence: float
    attempts: int
    cause: DifficultyCause | None
    last_outcome: Outcome | None

    @property
    def settled(self) -> bool:
        return self.status in {"met", "implied"}


@dataclass(frozen=True, slots=True)
class GoalGap:
    """A criterion still standing between the learner and the goal."""

    criterion_id: str
    statement: str
    status: CriterionStatus
    cause: DifficultyCause | None


# ---------------------------------------------------------------------------
# Requests and drafts crossing the language-model port
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FramingRequest:
    statement: str
    material: GoalMaterial
    profile: LearnerProfile
    maximum_criteria: int = MAX_CRITERIA


@dataclass(frozen=True, slots=True)
class CriterionDraft:
    statement: str
    depth: int


@dataclass(frozen=True, slots=True)
class GoalFraming:
    statement: str
    criteria: tuple[CriterionDraft, ...]


@dataclass(frozen=True, slots=True)
class StepSection:
    header: str
    icon: str = ""
    items: tuple[str, ...] = ()
    text: str = ""
    highlight: bool = False


@dataclass(frozen=True, slots=True)
class StepMaterial:
    title: str
    intro: str
    sections: tuple[StepSection, ...]


@dataclass(frozen=True, slots=True)
class StepRequest:
    goal: str
    criterion: SuccessCriterion
    activity: ActivityKind
    reason: RouteReason
    material: GoalMaterial
    profile: LearnerProfile
    previous_questions: tuple[str, ...] = ()
    observed_gaps: tuple[GoalGap, ...] = ()
    learner_reported_issue: str = ""

    @property
    def demand(self) -> Demand:
        return ACTIVITY_DEMAND[self.activity]


@dataclass(frozen=True, slots=True)
class StepDraft:
    material: StepMaterial
    question: str


@dataclass(frozen=True, slots=True)
class GoalStep:
    """A step handed to the learner, held server-side until it is answered."""

    step_id: str
    criterion_id: str
    activity: ActivityKind
    reason: RouteReason
    material: StepMaterial
    question: str


@dataclass(frozen=True, slots=True)
class StepAnswerRequest:
    goal: str
    criterion: SuccessCriterion
    step: GoalStep
    answer: str
    material: GoalMaterial
    profile: LearnerProfile


@dataclass(frozen=True, slots=True)
class StepEvaluation:
    outcome: Outcome
    cause: DifficultyCause
    feedback: str
    terms: tuple[DiscoveredTerm, ...] = ()
    patterns: tuple[DiscoveredPattern, ...] = ()

    @property
    def should_record(self) -> bool:
        """Off-task input is answered again, not written into the record."""
        return self.outcome != "garbage"


@dataclass(frozen=True, slots=True)
class SummaryRequest:
    goal: str
    profile: LearnerProfile
    material: GoalMaterial
    achieved: bool
    progress: tuple[CriterionProgress, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class SummaryDraft:
    narrative: str
    next_goal: str
    examples: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalReport:
    """What the learner takes away when the goal closes."""

    goal_id: str
    statement: str
    achieved: bool
    stopped_on_time: bool
    narrative: str
    next_goal: str
    proven: tuple[CriterionProgress, ...]
    shaky: tuple[CriterionProgress, ...]
    examples: tuple[str, ...]
    terms: tuple[DiscoveredTerm, ...]
    patterns: tuple[DiscoveredPattern, ...]


class GoalAuthor(Protocol):
    async def frame_goal(self, request: FramingRequest) -> GoalFraming: ...

    async def write_step(self, request: StepRequest) -> StepDraft: ...

    async def evaluate_step_answer(
        self, request: StepAnswerRequest
    ) -> StepEvaluation: ...

    async def write_goal_summary(self, request: SummaryRequest) -> SummaryDraft: ...


class IdentifierSource(Protocol):
    def new(self) -> str: ...


# ---------------------------------------------------------------------------
# Reading the evidence
# ---------------------------------------------------------------------------


def confidence_in(evidence: Sequence[Evidence]) -> float:
    """Fold answers into a bounded running confidence, newest weighing most."""
    value = _NEUTRAL_CONFIDENCE
    counted = [item for item in evidence if item.counts]
    if not counted:
        return value
    for item in counted:
        value += _LEARNING_RATE * (item.value - value)
    return min(1.0, max(0.0, value))


def progress_for(goal: LearningGoal, criterion: SuccessCriterion) -> CriterionProgress:
    """Derive one criterion's standing from everything observed so far.

    ``implied`` is the load-bearing status: a learner who has already met a
    deeper criterion has, by demonstration, cleared the shallower ones. Marking
    those implied rather than untested is what stops the route from walking a
    competent learner back through material they visibly do not need.
    """
    observed = goal.evidence_for(criterion.criterion_id)
    confidence = confidence_in(observed)
    last = observed[-1] if observed else None
    cause = _dominant_cause(observed)

    if not observed:
        status: CriterionStatus = (
            "implied" if _implied_by_deeper(goal, criterion) else "untested"
        )
        return CriterionProgress(criterion, status, confidence, 0, cause, None)

    if _meets(criterion, observed, confidence):
        status = "met"
    elif _implied_by_deeper(goal, criterion):
        status = "implied"
    elif confidence < _GAP_CONFIDENCE:
        status = "gap"
    else:
        status = "emerging"

    return CriterionProgress(
        criterion,
        status,
        confidence,
        len(observed),
        cause,
        last.outcome if last else None,
    )


def goal_progress(goal: LearningGoal) -> tuple[CriterionProgress, ...]:
    return tuple(progress_for(goal, criterion) for criterion in goal.criteria)


def gaps(goal: LearningGoal) -> tuple[GoalGap, ...]:
    """Criteria still in the way, shallowest first — the lesson's to-do list."""
    return tuple(
        GoalGap(
            criterion_id=item.criterion.criterion_id,
            statement=item.criterion.statement,
            status=item.status,
            cause=item.cause,
        )
        for item in sorted(
            (entry for entry in goal_progress(goal) if not entry.settled),
            key=lambda entry: entry.criterion.depth,
        )
    )


def goal_achieved(goal: LearningGoal) -> bool:
    """The goal is reached only when its deepest criterion is met unaided.

    Every other criterion may rest on an implication, but the top one has to
    have been demonstrated without scaffolding — otherwise "achieved" would
    only mean the learner followed a well-signposted path.
    """
    if not goal.criteria:
        return False
    deepest = goal.deepest
    assert deepest is not None
    progress = {item.criterion.criterion_id: item for item in goal_progress(goal)}
    if not all(item.settled for item in progress.values()):
        return False
    if progress[deepest.criterion_id].status != "met":
        return False
    return _has_unaided_proof(goal, deepest)


def time_exhausted(goal: LearningGoal) -> bool:
    return goal.spent_seconds >= goal.budget_seconds


def _meets(
    criterion: SuccessCriterion,
    observed: Sequence[Evidence],
    confidence: float,
) -> bool:
    if len(observed) < _MIN_ATTEMPTS_TO_MEET or confidence < _MET_CONFIDENCE:
        return False
    if observed[-1].outcome == "incorrect":
        return False
    return _has_demand_proof(observed, criterion.required_demand)


def _has_demand_proof(observed: Sequence[Evidence], required: Demand) -> bool:
    threshold = _DEMAND_RANK[required]
    return any(
        item.outcome == "correct" and _DEMAND_RANK[item.demand] >= threshold
        for item in observed
    )


def _has_unaided_proof(goal: LearningGoal, criterion: SuccessCriterion) -> bool:
    return any(
        item.activity == "apply_unaided" and item.outcome == "correct"
        for item in goal.evidence_for(criterion.criterion_id)
    )


def _implied_by_deeper(goal: LearningGoal, criterion: SuccessCriterion) -> bool:
    """True once a harder criterion has been answered correctly on merit.

    Getting the harder move right demonstrates the easier one inside it, so a
    single sound answer is enough to stop re-teaching below it — while the
    harder criterion itself still needs a run of answers to count as met. A
    lucky guess demonstrates nothing, and a later wrong answer withdraws the
    implication.
    """
    for other in goal.criteria:
        if other.depth <= criterion.depth:
            continue
        observed = goal.evidence_for(other.criterion_id)
        if not observed or observed[-1].outcome == "incorrect":
            continue
        if any(
            item.outcome == "correct" and item.cause != "lucky_guess"
            for item in observed
        ):
            return True
    return False


def _dominant_cause(observed: Sequence[Evidence]) -> DifficultyCause | None:
    """The cause worth acting on: the most recent one that is not 'unclear'."""
    for item in reversed(observed):
        if item.cause != "unclear":
            return item.cause
    return observed[-1].cause if observed else None


# ---------------------------------------------------------------------------
# Framing a wish into a checkable goal
# ---------------------------------------------------------------------------


def goal_id_for(
    statement: str, learning_language: str, kind: GoalKind = "standard"
) -> str:
    parts = [
        " ".join(statement.split()).casefold(),
        learning_language.strip().lower().replace("_", "-"),
    ]
    if kind != "standard":
        parts.append(kind)
    canonical = "\x1f".join(
        unicodedata.normalize("NFKC", part)
        for part in parts
    )
    return str(uuid.uuid5(_GOAL_NAMESPACE, canonical))


def state_goal(
    statement: str,
    profile: LearnerProfile,
    *,
    material: GoalMaterial = GoalMaterial(),
    created_at: float = 0.0,
    kind: GoalKind = "standard",
) -> LearningGoal:
    """Create an unframed goal — a stated result with no criteria yet."""
    cleaned = " ".join(statement.split())
    if not cleaned:
        raise ValueError("a learning goal must not be empty")
    if len(cleaned) > 200:
        raise ValueError("a learning goal is too long")
    return LearningGoal(
        goal_id=goal_id_for(cleaned, profile.learning_language, kind),
        statement=cleaned,
        profile=profile,
        kind=kind,
        material=_clean_material(material),
        created_at=created_at,
    )


class FrameGoal:
    """Turn a stated result into criteria that can actually be checked.

    "Learn Past Perfect" is not a stop condition; "use it correctly in a new
    story" is. The domain refuses a framing that offers nothing to demonstrate,
    and always keeps one criterion at production depth so the goal has a top.
    """

    def __init__(self, author: GoalAuthor, *, maximum_criteria: int = MAX_CRITERIA) -> None:
        if not 2 <= maximum_criteria <= 8:
            raise ValueError("a goal needs between two and eight criteria")
        self._author = author
        self._maximum_criteria = maximum_criteria

    async def execute(self, goal: LearningGoal) -> LearningGoal:
        framing = await self._author.frame_goal(
            FramingRequest(
                statement=goal.statement,
                material=goal.material,
                profile=goal.profile,
                maximum_criteria=self._maximum_criteria,
            )
        )
        criteria = _accept_criteria(framing.criteria, self._maximum_criteria)
        if len(criteria) < 2:
            raise ValueError("goal framing produced no checkable criteria")
        return replace(goal, criteria=criteria)


def _accept_criteria(
    drafts: Sequence[CriterionDraft], limit: int
) -> tuple[SuccessCriterion, ...]:
    """Keep distinct, depth-ordered criteria and guarantee a productive top."""
    seen: set[str] = set()
    accepted: list[tuple[str, int]] = []
    for draft in drafts:
        statement = " ".join(str(draft.statement).split())
        key = statement.casefold()
        if not statement or len(statement) > 200 or key in seen:
            continue
        depth = int(draft.depth)
        if not MIN_DEPTH <= depth <= MAX_DEPTH:
            continue
        seen.add(key)
        accepted.append((statement, depth))
        if len(accepted) == limit:
            break

    if not accepted:
        return ()
    accepted.sort(key=lambda item: item[1])
    accepted[-1] = (accepted[-1][0], MAX_DEPTH)
    return tuple(
        SuccessCriterion(f"c{index}", statement, depth)
        for index, (statement, depth) in enumerate(accepted, start=1)
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class GoalRoute:
    """Decides the next criterion and activity — purely, from the evidence.

    There is no fixed sequence of blocks to walk. The first step probes near
    the top of the goal so a capable learner is not marched through basics; the
    result of that probe, and of every answer after it, decides what comes next.
    """

    def plan(self, goal: LearningGoal) -> RoutePlan | None:
        if not goal.criteria:
            return None
        if goal_achieved(goal):
            return None

        progress = {item.criterion.criterion_id: item for item in goal_progress(goal)}
        if not goal.evidence:
            return self._diagnose(goal)

        unsettled = sorted(
            (item for item in progress.values() if not item.settled),
            key=lambda item: (item.criterion.depth, goal.criteria.index(item.criterion)),
        )
        if unsettled:
            return self._advance(goal, unsettled[0])
        return self._close_out(goal, progress)

    # -- first contact ----------------------------------------------------

    def _diagnose(self, goal: LearningGoal) -> RoutePlan:
        """Probe as deep as one question honestly can.

        Opening on the analytic band tells the route the most: clearing it
        implies the shallow criteria and sends the lesson straight to
        production, while missing it points at where the real gap starts.
        """
        analytic = [item for item in goal.criteria if item.depth < MAX_DEPTH]
        criterion = max(analytic or list(goal.criteria), key=lambda item: item.depth)
        return RoutePlan(
            criterion.criterion_id,
            self._pick(goal, criterion, _DEPTH_PROBE[criterion.depth], ()),
            "diagnose",
        )

    # -- the ordinary case ------------------------------------------------

    def _advance(self, goal: LearningGoal, progress: CriterionProgress) -> RoutePlan:
        criterion = progress.criterion
        observed = goal.evidence_for(criterion.criterion_id)
        recent = tuple(item.activity for item in observed[-2:])

        if not observed:
            return RoutePlan(
                criterion.criterion_id,
                self._pick(goal, criterion, _DEPTH_PROBE[criterion.depth], recent),
                "nearest_gap",
            )

        last = observed[-1]
        failed = last.outcome in {"incorrect", "vague"}
        if failed or last.cause in {"lucky_guess", "explains_not_produces"}:
            # A confident transfer is not something to repair; if it is
            # reported alongside a wrong answer, the cause tells us nothing.
            cause = "unclear" if failed and last.cause == "transfers_confidently" else last.cause
            return RoutePlan(
                criterion.criterion_id,
                self._pick(goal, criterion, _REPAIR[cause], recent),
                "repair_cause",
            )

        if not _has_demand_proof(observed, criterion.required_demand):
            wanted = _BY_DEMAND[criterion.required_demand][0]
            return RoutePlan(
                criterion.criterion_id,
                self._pick(goal, criterion, wanted, recent),
                "raise_demand",
            )

        # Right answer at the right demand, but not yet enough of a run to
        # call the criterion met: ask once more in a different shape.
        return RoutePlan(
            criterion.criterion_id,
            self._pick(goal, criterion, _BY_DEMAND[criterion.required_demand][0], recent),
            "consolidate",
        )

    # -- the last question ------------------------------------------------

    def _close_out(
        self, goal: LearningGoal, progress: dict[str, CriterionProgress]
    ) -> RoutePlan:
        deepest = goal.deepest
        assert deepest is not None
        if progress[deepest.criterion_id].status != "met":
            return RoutePlan(deepest.criterion_id, "create_example", "raise_demand")
        if goal.kind == "alphabet" and goal.profile.writing_support != "standard":
            completed = {
                item.activity
                for item in goal.evidence_for(deepest.criterion_id)
                if item.outcome == "correct"
            }
            if "handwrite_form" not in completed:
                return RoutePlan(deepest.criterion_id, "handwrite_form", "consolidate")
            if "type_on_keyboard" not in completed:
                return RoutePlan(deepest.criterion_id, "type_on_keyboard", "consolidate")
        return RoutePlan(deepest.criterion_id, "apply_unaided", "final_check")

    # -- activity selection ------------------------------------------------

    def _pick(
        self,
        goal: LearningGoal,
        criterion: SuccessCriterion,
        wanted: ActivityKind,
        recent: Sequence[ActivityKind],
    ) -> ActivityKind:
        """Honour the wanted activity, but never repeat the last one verbatim.

        Asking the same thing twice in a row teaches nothing about why the
        first attempt failed. When the wanted tier has no alternative left —
        a goal with no source material has only one receptive activity — the
        choice moves up a tier rather than repeating: a learner who just
        missed an explanation is better served by having to fix an error than
        by the same explanation again.
        """
        candidates: list[ActivityKind] = []
        for demand in _ESCALATION[ACTIVITY_DEMAND[wanted]]:
            candidates.extend(item for item in _BY_DEMAND[demand] if item not in candidates)
        candidates = [wanted, *(item for item in candidates if item != wanted)]

        usable = [item for item in candidates if self._available(goal, item)]
        if not usable:
            usable = [item for item in ACTIVITIES if self._available(goal, item)]
        fresh = [item for item in usable if item not in recent[-1:]]
        return (fresh or usable)[0]

    def _available(self, goal: LearningGoal, activity: ActivityKind) -> bool:
        if activity == "find_in_material":
            return goal.material.present
        if activity in {"handwrite_form", "type_on_keyboard"}:
            return goal.kind == "alphabet" and goal.profile.writing_support != "standard"
        return True


# ---------------------------------------------------------------------------
# Running a step
# ---------------------------------------------------------------------------


class BuildGoalStep:
    """Write the material and question for one planned step."""

    def __init__(self, author: GoalAuthor, identifiers: IdentifierSource) -> None:
        self._author = author
        self._identifiers = identifiers

    async def execute(
        self,
        goal: LearningGoal,
        plan: RoutePlan,
        *,
        previous_questions: Sequence[str] = (),
        learner_reported_issue: str = "",
    ) -> GoalStep:
        criterion = goal.criterion(plan.criterion_id)
        if criterion is None:
            raise ValueError("planned criterion does not belong to this goal")
        draft = await self._author.write_step(
            StepRequest(
                goal=goal.statement,
                criterion=criterion,
                activity=plan.activity,
                reason=plan.reason,
                material=goal.material,
                profile=goal.profile,
                previous_questions=tuple(previous_questions),
                observed_gaps=gaps(goal),
                learner_reported_issue=" ".join(learner_reported_issue.split())[:500],
            )
        )
        question = " ".join(draft.question.split())
        if not question:
            raise ValueError("goal author returned an empty question")
        return GoalStep(
            step_id=self._identifiers.new(),
            criterion_id=criterion.criterion_id,
            activity=plan.activity,
            reason=plan.reason,
            material=_clean_step_material(draft.material),
            question=question,
        )


class CheckGoalAnswer:
    """Judge an answer *and* name why it went that way."""

    def __init__(self, author: GoalAuthor) -> None:
        self._author = author

    async def execute(
        self, goal: LearningGoal, step: GoalStep, answer: str
    ) -> StepEvaluation:
        criterion = goal.criterion(step.criterion_id)
        if criterion is None:
            raise ValueError("answered criterion does not belong to this goal")
        cleaned = answer.strip()
        if not cleaned:
            return StepEvaluation("garbage", "unclear", "Please enter an answer.")

        result = await self._author.evaluate_step_answer(
            StepAnswerRequest(
                goal=goal.statement,
                criterion=criterion,
                step=step,
                answer=cleaned,
                material=goal.material,
                profile=goal.profile,
            )
        )
        if result.outcome not in _OUTCOME_VALUE:
            raise ValueError("goal author returned an invalid outcome")
        if result.cause not in CAUSES:
            raise ValueError("goal author returned an invalid difficulty cause")
        feedback = result.feedback.strip()
        if not feedback:
            raise ValueError("goal author returned empty feedback")
        return replace(
            result,
            feedback=feedback,
            terms=_clean_terms(result.terms),
            patterns=_clean_patterns(result.patterns),
        )


class RecordEvidence:
    """Append one observation to the goal and re-plan from it."""

    def __init__(self, route: GoalRoute, *, evidence_limit: int = MAX_EVIDENCE) -> None:
        if evidence_limit < 1:
            raise ValueError("evidence limit must be positive")
        self._route = route
        self._evidence_limit = evidence_limit

    def execute(
        self,
        goal: LearningGoal,
        step: GoalStep,
        evaluation: StepEvaluation,
        *,
        observed_at: float,
        answer: str = "",
        elapsed_seconds: float = 0.0,
    ) -> LearningGoal:
        if not evaluation.should_record:
            return goal

        evidence = Evidence(
            criterion_id=step.criterion_id,
            activity=step.activity,
            outcome=evaluation.outcome,
            cause=evaluation.cause,
            question=step.question,
            answer=" ".join(answer.split())[:1000],
            observed_at=max(0.0, observed_at),
        )
        updated = replace(
            goal,
            evidence=(*goal.evidence, evidence)[-self._evidence_limit :],
            terms=_merge_terms(goal.terms, evaluation.terms),
            patterns=_merge_patterns(goal.patterns, evaluation.patterns),
            spent_seconds=goal.spent_seconds + max(0.0, elapsed_seconds),
            last_worked_at=max(0.0, observed_at),
        )
        achieved = goal_achieved(updated)
        return replace(
            updated,
            next_plan=self._route.plan(updated),
            achieved_at=(
                updated.achieved_at
                if updated.achieved_at is not None
                else (observed_at if achieved else None)
            ),
        )


class CloseGoal:
    """Turn accumulated evidence into what the learner walks away with."""

    def __init__(self, author: GoalAuthor) -> None:
        self._author = author

    async def execute(self, goal: LearningGoal) -> GoalReport:
        if not goal.criteria:
            raise ValueError("cannot close a goal that was never framed")
        progress = goal_progress(goal)
        achieved = goal_achieved(goal)
        draft = await self._author.write_goal_summary(
            SummaryRequest(
                goal=goal.statement,
                profile=goal.profile,
                material=goal.material,
                achieved=achieved,
                progress=progress,
                evidence=tuple(item for item in goal.evidence if item.counts),
            )
        )
        return GoalReport(
            goal_id=goal.goal_id,
            statement=goal.statement,
            achieved=achieved,
            stopped_on_time=not achieved and time_exhausted(goal),
            narrative=draft.narrative.strip(),
            next_goal=" ".join(draft.next_goal.split()),
            proven=tuple(item for item in progress if item.settled),
            shaky=tuple(item for item in progress if not item.settled),
            examples=tuple(
                dict.fromkeys(
                    " ".join(str(value).split())
                    for value in draft.examples
                    if str(value).strip()
                )
            )[:6],
            terms=goal.terms,
            patterns=goal.patterns,
        )


class GoalReviewPolicy:
    """Which goal deserves the next reminder."""

    def needs_review(self, goal: LearningGoal) -> bool:
        return goal.framed and not goal_achieved(goal) and not time_exhausted(goal)

    def first_due(self, goals: Sequence[LearningGoal]) -> str | None:
        due = [goal for goal in goals if self.needs_review(goal)]
        if not due:
            return None
        return min(due, key=lambda goal: (goal.last_worked_at or 0.0, goal.statement)).statement


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _clean_material(material: GoalMaterial) -> GoalMaterial:
    return GoalMaterial(
        text=material.text.strip()[:20000],
        source_url=material.source_url.strip()[:2000],
    )


def _clean_step_material(material: StepMaterial) -> StepMaterial:
    title = " ".join(material.title.split())
    sections: list[StepSection] = []
    for section in material.sections:
        header = " ".join(section.header.split())
        items = tuple(item.strip() for item in section.items if item.strip())
        text = section.text.strip()
        if not header or (not items and not text):
            continue
        sections.append(
            StepSection(
                header=header,
                icon=section.icon.strip(),
                items=items,
                text=text,
                highlight=section.highlight,
            )
        )
    if not title or not sections:
        raise ValueError("goal author returned incomplete step material")
    return StepMaterial(title=title, intro=material.intro.strip(), sections=tuple(sections))


def _clean_terms(terms: Sequence[DiscoveredTerm]) -> tuple[DiscoveredTerm, ...]:
    accepted: list[DiscoveredTerm] = []
    seen: set[str] = set()
    for term in terms:
        word = " ".join(term.term.split())
        translation = " ".join(term.translation.split())
        key = word.casefold()
        if not word or not translation or key in seen:
            continue
        seen.add(key)
        accepted.append(
            DiscoveredTerm(word, translation, " ".join(term.context.split())[:500])
        )
    return tuple(accepted[:8])


def _clean_patterns(
    patterns: Sequence[DiscoveredPattern],
) -> tuple[DiscoveredPattern, ...]:
    accepted: list[DiscoveredPattern] = []
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        label = " ".join(pattern.label.split())
        category = pattern.category.strip()
        explanation = " ".join(pattern.explanation.split())
        example = " ".join(pattern.example.split())
        key = (category.casefold(), label.casefold())
        if not label or not category or not explanation or not example or key in seen:
            continue
        seen.add(key)
        accepted.append(DiscoveredPattern(category, label, explanation, example))
    return tuple(accepted[:6])


def _merge_terms(
    existing: Sequence[DiscoveredTerm], found: Sequence[DiscoveredTerm]
) -> tuple[DiscoveredTerm, ...]:
    known = {item.term.casefold() for item in existing}
    added = [item for item in found if item.term.casefold() not in known]
    return (*existing, *added)[:40]


def _merge_patterns(
    existing: Sequence[DiscoveredPattern], found: Sequence[DiscoveredPattern]
) -> tuple[DiscoveredPattern, ...]:
    known = {(item.category.casefold(), item.label.casefold()) for item in existing}
    added = [
        item
        for item in found
        if (item.category.casefold(), item.label.casefold()) not in known
    ]
    return (*existing, *added)[:20]
