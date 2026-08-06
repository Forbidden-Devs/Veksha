"""Adaptive Practice Planner — domain rules for vocabulary practice sessions.

A session no longer walks the due queue picking a random exercise format. It
plans a triple:

    lexical sense × trained skill × a task kind that can actually train it

FSRS still owns *when* a sense returns (see :mod:`skills` for the split). The
planner owns *what is asked about it*: it takes the due queue, finds the skill
that currently limits each sense, and picks a task format that exercises that
skill and is supported by the material at hand — a reverse-translation needs a
saved translation, a context task needs an observed sentence, a listening task
needs a client that can speak.

A wrong answer opens a bounded corrective chain (support task on the same
skill, then a transfer check on a fresh example) instead of only pushing the
FSRS interval down. Grading emits all four FSRS ratings, derived from the
checker's verdict, the response time, revealed hints, and whether the answer
came out of a corrective step; the learner can override the suggestion.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Literal, Protocol, Sequence

from .acquisition import LexicalItem
from .skills import (
    NEUTRAL_CONFIDENCE,
    Rating,
    RATINGS,
    Skill,
    SKILLS,
    SkillProfile,
    limiting_skill,
    record_attempt,
    weakness,
)


TaskKind = Literal[
    # recognition
    "translation",
    "synonym",
    "multiple_choice",
    # recall
    "reverse_translation",
    "cloze",
    "word_bank",
    # meaning in context
    "context_meaning",
    "usage_example",
    "sense_choice",
    # listening
    "listening_recall",
    "listening_cloze",
    "listening_choice",
]

Outcome = Literal["correct", "vague", "incorrect", "garbage"]
Stage = Literal["core", "support", "transfer"]
ReasonCode = Literal[
    "new_word",
    "recent_error",
    "weakest_skill",
    "due_review",
    "skill_rotation",
    "correction_support",
    "correction_transfer",
]
Resource = Literal["translation", "context", "audio"]


@dataclass(frozen=True, slots=True)
class SkillFormats:
    """Task kinds that train one skill, split by difficulty tier."""

    core: tuple[TaskKind, ...]
    support: TaskKind


# Every skill owns at least two core formats so a transfer check can use a
# different one than the task that was just failed.
SKILL_FORMATS: dict[Skill, SkillFormats] = {
    "recognition": SkillFormats(("translation", "synonym"), "multiple_choice"),
    "recall": SkillFormats(("reverse_translation", "cloze"), "word_bank"),
    "contextual_meaning": SkillFormats(
        ("context_meaning", "usage_example"), "sense_choice"
    ),
    "listening": SkillFormats(
        ("listening_recall", "listening_cloze"), "listening_choice"
    ),
}

TASK_SKILL: dict[TaskKind, Skill] = {
    kind: skill
    for skill, formats in SKILL_FORMATS.items()
    for kind in (*formats.core, formats.support)
}

TASK_REQUIREMENTS: dict[TaskKind, tuple[Resource, ...]] = {
    "translation": (),
    "synonym": (),
    "multiple_choice": ("translation",),
    "reverse_translation": ("translation",),
    "cloze": (),
    "word_bank": ("translation",),
    "context_meaning": ("context",),
    "usage_example": (),
    "sense_choice": ("context", "translation"),
    "listening_recall": ("audio",),
    "listening_cloze": ("audio",),
    "listening_choice": ("audio", "translation"),
}

CHOICE_KINDS: frozenset[TaskKind] = frozenset(
    {"multiple_choice", "word_bank", "sense_choice", "listening_choice"}
)
AUDIO_KINDS: frozenset[TaskKind] = frozenset(
    {"listening_recall", "listening_cloze", "listening_choice"}
)

MIN_OPTIONS = 3
MAX_OPTIONS = 4

# One support task plus one transfer check. Past that the sense goes back to
# the normal queue: a corrective chain must not stretch a session forever.
MAX_CORRECTION_STEPS = 2


# --------------------------------------------------------------------------
# Response-time windows
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResponseWindow:
    """Answer-time bounds that separate Easy from Good from Hard."""

    fast_seconds: float
    slow_seconds: float


_CHOICE_WINDOW = ResponseWindow(5.0, 18.0)
_SHORT_ANSWER_WINDOW = ResponseWindow(8.0, 35.0)
_SENTENCE_WINDOW = ResponseWindow(15.0, 60.0)

_SENTENCE_KINDS: frozenset[TaskKind] = frozenset({"usage_example", "context_meaning"})


def response_window(kind: TaskKind) -> ResponseWindow:
    if kind in CHOICE_KINDS:
        return _CHOICE_WINDOW
    if kind in _SENTENCE_KINDS:
        return _SENTENCE_WINDOW
    return _SHORT_ANSWER_WINDOW


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LearnerCapabilities:
    """What the connected client can actually present."""

    audio: bool = False


@dataclass(frozen=True, slots=True)
class PlanReason:
    """Why this exercise appeared, in a form the client can localize."""

    code: ReasonCode
    skill: Skill


@dataclass(frozen=True, slots=True)
class PracticePlan:
    item: LexicalItem
    skill: Skill
    kind: TaskKind
    reason: PlanReason
    stage: Stage = "core"
    avoid_contexts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskDraftRequest:
    item: LexicalItem
    kind: TaskKind
    skill: Skill
    stage: Stage
    proficiency: str
    native_language: str
    learning_language: str
    avoid_contexts: tuple[str, ...] = ()
    option_count: int = 0


@dataclass(frozen=True, slots=True)
class TaskDraft:
    question: str
    expected_answer: str = ""
    options: tuple[str, ...] = ()
    audio_text: str = ""
    hint: str = ""


@dataclass(frozen=True, slots=True)
class PracticeTask:
    task_id: str
    item_id: str
    word: str
    context: str
    kind: TaskKind
    skill: Skill
    stage: Stage
    question: str
    review_count: int
    reason: PlanReason
    expected_answer: str = ""
    options: tuple[str, ...] = ()
    audio_text: str = ""
    hint: str = ""

    @property
    def counts_as_review(self) -> bool:
        """Only the planned task reschedules the sense; repairs do not."""
        return self.stage == "core"


@dataclass(frozen=True, slots=True)
class AnswerCheckRequest:
    task: PracticeTask
    answer: str
    proficiency: str
    native_language: str
    learning_language: str


@dataclass(frozen=True, slots=True)
class AnswerEvaluation:
    outcome: Outcome
    feedback: str
    error_note: str = ""

    @property
    def is_answer(self) -> bool:
        """False only for empty or off-task input, which is not a review."""
        return self.outcome != "garbage"

    @property
    def failed(self) -> bool:
        return self.outcome == "incorrect"


class PracticeContentProvider(Protocol):
    async def draft_task(self, request: TaskDraftRequest) -> TaskDraft: ...

    async def evaluate_answer(self, request: AnswerCheckRequest) -> AnswerEvaluation: ...


class ChoiceSource(Protocol):
    def choose(self, values: Sequence[TaskKind]) -> TaskKind: ...


class IdentifierSource(Protocol):
    def new(self) -> str: ...


def available_resources(
    item: LexicalItem, capabilities: LearnerCapabilities
) -> frozenset[Resource]:
    resources: set[Resource] = set()
    if item.translation.strip():
        resources.add("translation")
    if item.contexts:
        resources.add("context")
    if capabilities.audio:
        resources.add("audio")
    return frozenset(resources)


def feasible_kinds(
    kinds: Iterable[TaskKind], resources: frozenset[Resource]
) -> tuple[TaskKind, ...]:
    return tuple(
        kind for kind in kinds if resources.issuperset(TASK_REQUIREMENTS[kind])
    )


def trainable_skills(
    item: LexicalItem, capabilities: LearnerCapabilities
) -> tuple[Skill, ...]:
    """Skills with at least one usable core format for this sense."""
    resources = available_resources(item, capabilities)
    return tuple(
        skill
        for skill in SKILLS
        if feasible_kinds(SKILL_FORMATS[skill].core, resources)
    )


class PracticeQueue:
    """Availability filter: which senses may be practiced at all right now."""

    def __init__(self, review_horizon_seconds: float) -> None:
        if review_horizon_seconds < 0:
            raise ValueError("review horizon must not be negative")
        self._review_horizon_seconds = review_horizon_seconds

    @property
    def review_horizon_seconds(self) -> float:
        return self._review_horizon_seconds

    def available(
        self,
        items: Sequence[LexicalItem],
        *,
        learning_language: str,
        now: float,
        excluded: set[str] | None = None,
    ) -> list[LexicalItem]:
        excluded_ids = excluded or set()
        language = _language_base(learning_language)
        horizon = now + self._review_horizon_seconds

        active = [
            item
            for item in items
            if item.status == "learning"
            and item.item_id not in excluded_ids
            and _language_base(item.language) == language
        ]
        due = [
            item
            for item in active
            if item.schedule.review_count >= 0
            and item.schedule.next_review_at <= horizon
        ]
        new = [item for item in active if item.schedule.review_count < 0]
        due.sort(
            key=lambda item: (
                item.schedule.next_review_at,
                item.term.casefold(),
                item.item_id,
            )
        )
        new.sort(
            key=lambda item: (
                item.schedule.added_at,
                item.term.casefold(),
                item.item_id,
            )
        )
        return due + new


@dataclass
class SessionMemory:
    """What this session already showed, so it does not repeat itself."""

    used_items: set[str] = field(default_factory=set)
    kind_counts: dict[TaskKind, int] = field(default_factory=dict)
    skill_counts: dict[Skill, int] = field(default_factory=dict)
    last_kind: TaskKind | None = None

    def record(self, plan: PracticePlan) -> None:
        self.used_items.add(plan.item.item_id)
        self.kind_counts[plan.kind] = self.kind_counts.get(plan.kind, 0) + 1
        self.skill_counts[plan.skill] = self.skill_counts.get(plan.skill, 0) + 1
        self.last_kind = plan.kind


class PracticePlanner:
    """Scores the due queue over senses *and* skills, then picks a format."""

    # Urgency and weakness are deliberately close in weight: a session should
    # respect FSRS without spending itself on the skill a learner already has.
    URGENCY_WEIGHT = 0.55
    WEAKNESS_WEIGHT = 0.45
    RECENT_ERROR_BONUS = 0.15
    # Seen-before penalties keep a session from turning into ten cloze tasks.
    KIND_FATIGUE = 0.12
    SKILL_FATIGUE = 0.07
    REPEAT_KIND_PENALTY = 0.25

    _NEW_ITEM_PRIORITY = 0.55
    _DUE_BASE_PRIORITY = 0.6
    _OVERDUE_DAY_WEIGHT = 0.1
    # A skill counts as "the" weak one only when it is clearly below its peers.
    _WEAKNESS_MARGIN = 0.1

    def __init__(self, queue: PracticeQueue, choices: ChoiceSource) -> None:
        self._queue = queue
        self._choices = choices

    def plan(
        self,
        items: Sequence[LexicalItem],
        *,
        learning_language: str,
        now: float,
        memory: SessionMemory,
        capabilities: LearnerCapabilities,
    ) -> PracticePlan | None:
        candidates = self._queue.available(
            items,
            learning_language=learning_language,
            now=now,
            excluded=memory.used_items,
        )

        best: tuple[float, int, PracticePlan] | None = None
        for order, item in enumerate(candidates):
            scored = self._score_item(
                item, now=now, memory=memory, capabilities=capabilities
            )
            if scored is None:
                continue
            score, plan = scored
            # `order` breaks ties by queue position, keeping planning stable.
            if best is None or score > best[0] or (score == best[0] and order < best[1]):
                best = (score, order, plan)
        return best[2] if best else None

    def _score_item(
        self,
        item: LexicalItem,
        *,
        now: float,
        memory: SessionMemory,
        capabilities: LearnerCapabilities,
    ) -> tuple[float, PracticePlan] | None:
        resources = available_resources(item, capabilities)
        skills = trainable_skills(item, capabilities)
        if not skills:
            return None

        priority = self._priority(item, now=now)
        best: tuple[float, PracticePlan] | None = None
        for skill in skills:
            state = item.skills.state(skill)
            kinds = feasible_kinds(SKILL_FORMATS[skill].core, resources)
            kind = self._pick_kind(kinds, memory)

            score = (
                self.URGENCY_WEIGHT * priority
                + self.WEAKNESS_WEIGHT * weakness(state, now=now)
                - self.KIND_FATIGUE * memory.kind_counts.get(kind, 0)
                - self.SKILL_FATIGUE * memory.skill_counts.get(skill, 0)
            )
            if state.failing:
                score += self.RECENT_ERROR_BONUS
            if memory.last_kind == kind:
                score -= self.REPEAT_KIND_PENALTY

            if best is None or score > best[0]:
                best = (
                    score,
                    PracticePlan(
                        item=item,
                        skill=skill,
                        kind=kind,
                        reason=self._reason(item, skill, skills, now=now),
                    ),
                )
        return best

    def _pick_kind(
        self, kinds: tuple[TaskKind, ...], memory: SessionMemory
    ) -> TaskKind:
        if not kinds:
            raise ValueError("skill has no feasible task kind")
        fewest = min(memory.kind_counts.get(kind, 0) for kind in kinds)
        rested = tuple(
            kind for kind in kinds if memory.kind_counts.get(kind, 0) == fewest
        )
        unrepeated = tuple(kind for kind in rested if kind != memory.last_kind)
        return self._choices.choose(unrepeated or rested)

    def _priority(self, item: LexicalItem, *, now: float) -> float:
        schedule = item.schedule
        if schedule.review_count < 0:
            return self._NEW_ITEM_PRIORITY
        overdue_days = max(0.0, (now - schedule.next_review_at) / 86400)
        return min(
            1.0, self._DUE_BASE_PRIORITY + self._OVERDUE_DAY_WEIGHT * overdue_days
        )

    def _reason(
        self,
        item: LexicalItem,
        skill: Skill,
        skills: tuple[Skill, ...],
        *,
        now: float,
    ) -> PlanReason:
        state = item.skills.state(skill)
        if state.failing:
            return PlanReason("recent_error", skill)
        if item.schedule.review_count < 0:
            return PlanReason("new_word", skill)
        others = [
            item.skills.state(other).confidence for other in skills if other != skill
        ]
        if others and state.confidence + self._WEAKNESS_MARGIN <= max(others):
            return PlanReason("weakest_skill", skill)
        if item.schedule.review_count >= 0 and item.schedule.next_review_at <= now:
            return PlanReason("due_review", skill)
        return PlanReason("skill_rotation", skill)


# --------------------------------------------------------------------------
# Building and checking tasks
# --------------------------------------------------------------------------


class BuildPracticeTask:
    """Turns a plan into a checked, presentable task."""

    def __init__(
        self,
        provider: PracticeContentProvider,
        identifiers: IdentifierSource,
    ) -> None:
        self._provider = provider
        self._identifiers = identifiers

    async def execute(
        self,
        plan: PracticePlan,
        *,
        proficiency: str,
        native_language: str,
        learning_language: str,
    ) -> PracticeTask:
        item = plan.item
        draft = await self._provider.draft_task(
            TaskDraftRequest(
                item=item,
                kind=plan.kind,
                skill=plan.skill,
                stage=plan.stage,
                proficiency=proficiency,
                native_language=native_language,
                learning_language=learning_language,
                avoid_contexts=plan.avoid_contexts,
                option_count=MAX_OPTIONS if plan.kind in CHOICE_KINDS else 0,
            )
        )

        question = draft.question.strip()
        if not question:
            raise ValueError("practice provider returned an empty question")

        options = _clean_options(draft.options)
        expected = draft.expected_answer.strip()
        if plan.kind in CHOICE_KINDS:
            if len(options) < MIN_OPTIONS:
                raise ValueError("choice task needs several answer options")
            if not _contains_option(options, expected):
                raise ValueError("choice task options omit the expected answer")
        else:
            options = ()

        audio_text = draft.audio_text.strip()
        if plan.kind in AUDIO_KINDS and not audio_text:
            raise ValueError("listening task returned nothing to voice")
        if plan.kind not in AUDIO_KINDS:
            audio_text = ""

        return PracticeTask(
            task_id=self._identifiers.new(),
            item_id=item.item_id,
            word=item.term,
            context=item.latest_context,
            kind=plan.kind,
            skill=plan.skill,
            stage=plan.stage,
            question=question,
            review_count=item.schedule.review_count,
            reason=plan.reason,
            expected_answer=expected,
            options=options,
            audio_text=audio_text,
            hint=draft.hint.strip(),
        )


class CheckPracticeAnswer:
    def __init__(self, provider: PracticeContentProvider) -> None:
        self._provider = provider

    async def execute(self, request: AnswerCheckRequest) -> AnswerEvaluation:
        answer = request.answer.strip()
        if not answer:
            return AnswerEvaluation("garbage", "Please enter an answer.")
        normalized = AnswerCheckRequest(
            task=request.task,
            answer=answer,
            proficiency=request.proficiency.strip(),
            native_language=request.native_language.strip() or "en",
            learning_language=request.learning_language.strip() or "en",
        )
        result = await self._provider.evaluate_answer(normalized)
        if result.outcome not in {"correct", "vague", "incorrect", "garbage"}:
            raise ValueError("practice provider returned an invalid outcome")
        if not result.feedback.strip():
            raise ValueError("practice provider returned empty feedback")
        return AnswerEvaluation(
            outcome=result.outcome,
            feedback=result.feedback.strip(),
            error_note=result.error_note.strip(),
        )


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------


def suggest_rating(
    kind: TaskKind,
    outcome: Outcome,
    *,
    response_seconds: float = 0.0,
    hints_used: int = 0,
    corrected: bool = False,
) -> Rating | None:
    """Derive an FSRS rating from the verdict, the clock, and the hints used.

    Returns ``None`` for non-answers, which are not reviews at all.
    """
    if outcome == "garbage":
        return None
    if outcome == "incorrect":
        return "again"
    if outcome == "vague":
        return "hard"

    # A correct answer that needed help, or arrived after a repair, is Hard:
    # the learner produced it, but not from a memory that will hold.
    if corrected or hints_used > 0:
        return "hard"
    window = response_window(kind)
    if response_seconds > window.slow_seconds:
        return "hard"
    if 0 < response_seconds <= window.fast_seconds:
        return "easy"
    return "good"


@dataclass(frozen=True, slots=True)
class CorrectionStep:
    """The next repair task queued for a sense the learner just missed."""

    item_id: str
    skill: Skill
    stage: Stage
    avoid_kinds: tuple[TaskKind, ...] = ()
    avoid_contexts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GradedAnswer:
    task: PracticeTask
    outcome: Outcome
    feedback: str
    error_note: str
    rating: Rating | None
    suggested_rating: Rating | None
    manual_rating: bool
    counts_as_review: bool
    correction: CorrectionStep | None
    profile: SkillProfile


@dataclass(frozen=True, slots=True)
class SkillReport:
    skill: Skill
    confidence: float
    attempts: int


@dataclass(frozen=True, slots=True)
class ItemReport:
    item_id: str
    term: str
    consolidated: bool
    limiting_skill: Skill
    limiting_confidence: float


@dataclass(frozen=True, slots=True)
class SessionSummary:
    reviewed: int
    corrections: int
    skills: tuple[tuple[Skill, int], ...]
    items: tuple[ItemReport, ...]


class PracticeSession:
    """Session state machine: plans, grades, and repairs — without any I/O."""

    def __init__(
        self,
        planner: PracticePlanner,
        *,
        target_tasks: int,
        capabilities: LearnerCapabilities,
        learning_language: str,
    ) -> None:
        if target_tasks < 0:
            raise ValueError("target task count must not be negative")
        self._planner = planner
        self._target = target_tasks
        self._capabilities = capabilities
        self._learning_language = learning_language
        self._memory = SessionMemory()
        self._repairs: deque[CorrectionStep] = deque()
        self._active: dict[str, PracticeTask] = {}
        self._plans: dict[str, PracticePlan] = {}
        self._items: dict[str, LexicalItem] = {}
        self._profiles: dict[str, SkillProfile] = {}
        self._repair_steps: dict[str, int] = {}
        self._unresolved: set[str] = set()
        self._asked_contexts: dict[str, tuple[str, ...]] = {}
        self._failed_kinds: dict[str, tuple[TaskKind, ...]] = {}
        self._reviewed = 0
        self._corrections = 0
        self._planned = 0

    # -- session shape ------------------------------------------------------

    @property
    def target(self) -> int:
        return self._target

    @property
    def reviewed(self) -> int:
        return self._reviewed

    @property
    def capabilities(self) -> LearnerCapabilities:
        return self._capabilities

    def exclude(self, item_ids: Iterable[str]) -> None:
        self._memory.used_items.update(str(value) for value in item_ids)

    def drop_item(self, item_id: str) -> None:
        """Remove a sense from the session — it was marked as already known."""
        self._memory.used_items.add(item_id)
        self._repairs = deque(step for step in self._repairs if step.item_id != item_id)
        self._unresolved.discard(item_id)
        for task_id, task in tuple(self._active.items()):
            if task.item_id == item_id:
                self._forget_task(task_id)
        # Lowering the target keeps the progress bar honest about what is left.
        if self._target > 0:
            self._target -= 1

    def task(self, task_id: str) -> PracticeTask | None:
        return self._active.get(task_id)

    # -- planning -----------------------------------------------------------

    def plan_next(
        self, items: Sequence[LexicalItem], *, now: float
    ) -> PracticePlan | None:
        """The repair queue first, then a freshly planned exercise."""
        index = {item.item_id: item for item in items}
        while self._repairs:
            step = self._repairs.popleft()
            item = index.get(step.item_id) or self._items.get(step.item_id)
            if item is None:
                continue
            plan = self._repair_plan(step, item)
            if plan is not None:
                return plan

        if self._planned >= self._target:
            return None
        return self._planner.plan(
            items,
            learning_language=self._learning_language,
            now=now,
            memory=self._memory,
            capabilities=self._capabilities,
        )

    def _repair_plan(self, step: CorrectionStep, item: LexicalItem) -> PracticePlan | None:
        resources = available_resources(item, self._capabilities)
        formats = SKILL_FORMATS[step.skill]
        candidates = (
            (formats.support,)
            if step.stage == "support"
            else tuple(kind for kind in formats.core if kind not in step.avoid_kinds)
        )
        feasible = feasible_kinds(candidates, resources)
        if not feasible and step.stage == "transfer":
            # No unused core format left; a repeat of the failed one still
            # checks transfer as long as the example is new.
            feasible = feasible_kinds(formats.core, resources)
        if not feasible:
            self._unresolved.add(item.item_id)
            return None
        code: ReasonCode = (
            "correction_support" if step.stage == "support" else "correction_transfer"
        )
        return PracticePlan(
            item=item,
            skill=step.skill,
            kind=feasible[0],
            reason=PlanReason(code, step.skill),
            stage=step.stage,
            avoid_contexts=step.avoid_contexts,
        )

    def register(self, plan: PracticePlan, task: PracticeTask) -> None:
        self._active[task.task_id] = task
        self._plans[task.task_id] = plan
        self._items[plan.item.item_id] = plan.item
        self._profiles.setdefault(plan.item.item_id, plan.item.skills)
        if plan.stage == "core":
            self._memory.record(plan)
            self._planned += 1
        else:
            self._corrections += 1
        if task.context:
            seen = self._asked_contexts.get(task.item_id, ())
            if task.context not in seen:
                self._asked_contexts[task.item_id] = (*seen, task.context)

    # -- grading ------------------------------------------------------------

    def grade(
        self,
        task: PracticeTask,
        evaluation: AnswerEvaluation,
        *,
        now: float,
        response_seconds: float = 0.0,
        hints_used: int = 0,
        requested_rating: str | None = None,
    ) -> GradedAnswer:
        suggested = suggest_rating(
            task.kind,
            evaluation.outcome,
            response_seconds=response_seconds,
            hints_used=hints_used,
            corrected=task.stage != "core",
        )
        rating = suggested
        manual = False
        if suggested is not None and requested_rating in RATINGS:
            manual = requested_rating != suggested
            rating = requested_rating  # type: ignore[assignment]

        profile = self._profiles.get(task.item_id, SkillProfile())
        correction: CorrectionStep | None = None

        if rating is not None:
            profile = profile.with_state(
                task.skill,
                record_attempt(profile.state(task.skill), rating, now=now),
            )
            self._profiles[task.item_id] = profile
            self._forget_task(task.task_id)
            if task.counts_as_review:
                self._reviewed += 1
            correction = self._advance_chain(task, rating)

        return GradedAnswer(
            task=task,
            outcome=evaluation.outcome,
            feedback=evaluation.feedback,
            error_note=evaluation.error_note,
            rating=rating,
            suggested_rating=suggested,
            manual_rating=manual,
            counts_as_review=task.counts_as_review and rating is not None,
            correction=correction,
            profile=profile,
        )

    def _advance_chain(self, task: PracticeTask, rating: Rating) -> CorrectionStep | None:
        item_id = task.item_id
        steps = self._repair_steps.get(item_id, 0)

        if task.stage == "core":
            if rating != "again":
                self._unresolved.discard(item_id)
                return None
            self._unresolved.add(item_id)
            failed = self._failed_kinds.get(item_id, ())
            self._failed_kinds[item_id] = (*failed, task.kind)
            return self._queue_repair(
                CorrectionStep(item_id, task.skill, "support", (task.kind,)),
                steps,
            )

        if task.stage == "support":
            if rating == "again":
                # A failed support task ends the chain: repeating it here would
                # only drill a sense the learner cannot hold on to right now.
                return None
            # The transfer check must avoid the format that was missed, not the
            # eased one that was just passed — that is what makes it transfer.
            return self._queue_repair(
                CorrectionStep(
                    item_id,
                    task.skill,
                    "transfer",
                    self._failed_kinds.get(item_id, (task.kind,)),
                    self._asked_contexts.get(item_id, ()),
                ),
                steps,
            )

        # transfer: the chain is done either way; the sense returns to the queue
        if rating != "again":
            self._unresolved.discard(item_id)
        return None

    def _queue_repair(self, step: CorrectionStep, steps: int) -> CorrectionStep | None:
        if steps >= MAX_CORRECTION_STEPS:
            return None
        self._repair_steps[step.item_id] = steps + 1
        self._repairs.append(step)
        return step

    def _forget_task(self, task_id: str) -> None:
        self._active.pop(task_id, None)
        self._plans.pop(task_id, None)

    # -- reporting ----------------------------------------------------------

    def summary(self) -> SessionSummary:
        items: list[ItemReport] = []
        for item_id, profile in self._profiles.items():
            item = self._items.get(item_id)
            if item is None:
                continue
            trainable = trainable_skills(item, self._capabilities) or SKILLS
            weakest = limiting_skill(profile, candidates=trainable)
            items.append(
                ItemReport(
                    item_id=item_id,
                    term=item.term,
                    consolidated=item_id not in self._unresolved,
                    limiting_skill=weakest,
                    limiting_confidence=profile.state(weakest).confidence,
                )
            )
        items.sort(key=lambda report: (report.consolidated, report.term.casefold()))
        return SessionSummary(
            reviewed=self._reviewed,
            corrections=self._corrections,
            skills=tuple(
                (skill, self._memory.skill_counts[skill])
                for skill in SKILLS
                if self._memory.skill_counts.get(skill)
            ),
            items=tuple(items),
        )


def aggregate_skills(items: Sequence[LexicalItem]) -> tuple[SkillReport, ...]:
    """Mean confidence per skill across senses, for the session's progress row."""
    reports: list[SkillReport] = []
    for skill in SKILLS:
        states = [item.skills.state(skill) for item in items]
        practiced = [state for state in states if state.practiced]
        confidence = (
            sum(state.confidence for state in practiced) / len(practiced)
            if practiced
            else NEUTRAL_CONFIDENCE
        )
        reports.append(
            SkillReport(
                skill=skill,
                confidence=confidence,
                attempts=sum(state.attempts for state in states),
            )
        )
    return tuple(reports)


def _clean_options(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    options: list[str] = []
    for value in values:
        text = " ".join(str(value).split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        options.append(text)
    return tuple(options[:MAX_OPTIONS])


def _contains_option(options: Sequence[str], expected: str) -> bool:
    key = " ".join(expected.split()).casefold()
    return bool(key) and any(option.casefold() == key for option in options)


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


__all__ = [
    "AnswerCheckRequest",
    "AnswerEvaluation",
    "BuildPracticeTask",
    "CheckPracticeAnswer",
    "CorrectionStep",
    "GradedAnswer",
    "ItemReport",
    "LearnerCapabilities",
    "MAX_CORRECTION_STEPS",
    "Outcome",
    "PlanReason",
    "PracticePlan",
    "PracticePlanner",
    "PracticeQueue",
    "PracticeSession",
    "PracticeTask",
    "Rating",
    "SessionSummary",
    "Skill",
    "SkillProfile",
    "SkillReport",
    "Stage",
    "TaskDraft",
    "TaskDraftRequest",
    "TaskKind",
    "aggregate_skills",
    "suggest_rating",
]
