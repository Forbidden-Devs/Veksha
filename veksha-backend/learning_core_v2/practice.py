"""Domain rules for vocabulary practice sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence, TypeVar

from .acquisition import LexicalItem


TaskKind = Literal["translation", "synonym", "example", "reverse_translation"]
Outcome = Literal["correct", "vague", "incorrect", "garbage"]


@dataclass(frozen=True, slots=True)
class TaskDraftRequest:
    item: LexicalItem
    kind: TaskKind
    proficiency: str
    native_language: str
    learning_language: str


@dataclass(frozen=True, slots=True)
class TaskDraft:
    question: str
    skill: str
    reverse_text: str = ""


@dataclass(frozen=True, slots=True)
class PracticeTask:
    task_id: str
    item_id: str
    word: str
    context: str
    kind: TaskKind
    question: str
    review_count: int
    skill: str
    reverse_text: str = ""


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

    @property
    def should_update_schedule(self) -> bool:
        return self.outcome != "garbage"


class PracticeContentProvider(Protocol):
    async def draft_task(self, request: TaskDraftRequest) -> TaskDraft: ...

    async def evaluate_answer(self, request: AnswerCheckRequest) -> AnswerEvaluation: ...


T = TypeVar("T")


class ChoiceSource(Protocol):
    def choose(self, values: Sequence[T]) -> T: ...


class IdentifierSource(Protocol):
    def new(self) -> str: ...


class PracticeQueue:
    def __init__(self, review_horizon_seconds: float) -> None:
        if review_horizon_seconds < 0:
            raise ValueError("review horizon must not be negative")
        self._review_horizon_seconds = review_horizon_seconds

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


class BuildPracticeTask:
    def __init__(
        self,
        provider: PracticeContentProvider,
        choices: ChoiceSource,
        identifiers: IdentifierSource,
    ) -> None:
        self._provider = provider
        self._choices = choices
        self._identifiers = identifiers

    async def execute(
        self,
        item: LexicalItem,
        *,
        proficiency: str,
        native_language: str,
        learning_language: str,
    ) -> PracticeTask:
        kinds: list[TaskKind] = ["translation", "synonym", "example"]
        if item.translation.strip():
            kinds.append("reverse_translation")
        kind = self._choices.choose(kinds)
        draft = await self._provider.draft_task(
            TaskDraftRequest(
                item=item,
                kind=kind,
                proficiency=proficiency,
                native_language=native_language,
                learning_language=learning_language,
            )
        )
        question = draft.question.strip()
        if not question:
            raise ValueError("practice provider returned an empty question")
        return PracticeTask(
            task_id=self._identifiers.new(),
            item_id=item.item_id,
            word=item.term,
            context=item.latest_context,
            kind=kind,
            question=question,
            review_count=item.schedule.review_count,
            skill=draft.skill.strip(),
            reverse_text=draft.reverse_text.strip(),
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
        return AnswerEvaluation(result.outcome, result.feedback.strip())


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]
