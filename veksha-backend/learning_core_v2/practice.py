"""Domain rules for vocabulary practice sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence, TypeVar


TaskKind = Literal["translation", "synonym", "example", "reverse_translation"]
Outcome = Literal["correct", "vague", "incorrect", "garbage"]


@dataclass(frozen=True, slots=True)
class PracticeWord:
    text: str
    language: str
    context: str = ""
    translation: str = ""
    review_count: int = -1
    next_review_at: float = 0.0
    added_at: float = 0.0
    known: bool = False


@dataclass(frozen=True, slots=True)
class TaskDraftRequest:
    word: PracticeWord
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
        words: Sequence[PracticeWord],
        *,
        learning_language: str,
        now: float,
        excluded: set[str] | None = None,
    ) -> list[PracticeWord]:
        excluded_keys = {value.casefold() for value in (excluded or set())}
        language = _language_base(learning_language)
        horizon = now + self._review_horizon_seconds

        active = [
            word
            for word in words
            if not word.known
            and word.text.casefold() not in excluded_keys
            and _language_base(word.language) == language
        ]
        due = [
            word
            for word in active
            if word.review_count >= 0 and word.next_review_at <= horizon
        ]
        new = [word for word in active if word.review_count < 0]
        due.sort(key=lambda word: (word.next_review_at, word.text.casefold()))
        new.sort(key=lambda word: (word.added_at, word.text.casefold()))
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
        word: PracticeWord,
        *,
        proficiency: str,
        native_language: str,
        learning_language: str,
    ) -> PracticeTask:
        kinds: list[TaskKind] = ["translation", "synonym", "example"]
        if word.translation.strip():
            kinds.append("reverse_translation")
        kind = self._choices.choose(kinds)
        draft = await self._provider.draft_task(
            TaskDraftRequest(
                word=word,
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
            word=word.text,
            context=word.context,
            kind=kind,
            question=question,
            review_count=word.review_count,
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
