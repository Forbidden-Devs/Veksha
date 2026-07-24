"""Independent domain model and use cases for topic lessons."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol


LessonOutcome = Literal["correct", "vague", "incorrect", "garbage"]


@dataclass(frozen=True, slots=True)
class LessonSection:
    header: str
    icon: str = ""
    items: tuple[str, ...] = ()
    text: str = ""
    highlight: bool = False


@dataclass(frozen=True, slots=True)
class LessonMaterial:
    title: str
    intro: str
    sections: tuple[LessonSection, ...]


@dataclass(frozen=True, slots=True)
class LessonAttempt:
    question: str
    outcome: LessonOutcome


@dataclass(frozen=True, slots=True)
class LessonUnit:
    name: str
    material: LessonMaterial | None = None
    mastery: float = 0.0
    history: tuple[LessonAttempt, ...] = ()


@dataclass(frozen=True, slots=True)
class LessonTopic:
    name: str
    units: tuple[LessonUnit, ...] = ()
    curriculum_exhausted: bool = False
    last_reviewed_at: float | None = None


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    proficiency: str
    native_language: str
    learning_language: str
    goals: str = ""


@dataclass(frozen=True, slots=True)
class CurriculumRequest:
    topic: str
    existing_units: tuple[str, ...]
    requested_count: int
    profile: LearnerProfile


@dataclass(frozen=True, slots=True)
class MaterialRequest:
    topic: str
    unit: str
    neighboring_units: tuple[str, ...]
    profile: LearnerProfile


@dataclass(frozen=True, slots=True)
class QuestionRequest:
    topic: str
    unit: LessonUnit
    previous_questions: tuple[str, ...]
    profile: LearnerProfile


@dataclass(frozen=True, slots=True)
class AnswerRequest:
    topic: str
    unit: LessonUnit
    question: str
    answer: str
    profile: LearnerProfile


@dataclass(frozen=True, slots=True)
class LessonEvaluation:
    outcome: LessonOutcome
    feedback: str

    @property
    def should_record(self) -> bool:
        return self.outcome != "garbage"


@dataclass(frozen=True, slots=True)
class LessonQuestion:
    question_id: str
    unit_name: str
    text: str


@dataclass(frozen=True, slots=True)
class RecordedAnswer:
    question: str
    outcome: LessonOutcome


@dataclass(frozen=True, slots=True)
class PreparedLesson:
    topic: LessonTopic
    units: tuple[LessonUnit, ...]


@dataclass(frozen=True, slots=True)
class TopicSummary:
    name: str
    unit_count: int
    mastery: float
    last_reviewed_at: float | None


class LessonAuthor(Protocol):
    async def propose_units(self, request: CurriculumRequest) -> Sequence[str]: ...

    async def write_material(self, request: MaterialRequest) -> LessonMaterial: ...

    async def write_question(self, request: QuestionRequest) -> str: ...

    async def evaluate_lesson_answer(
        self, request: AnswerRequest
    ) -> LessonEvaluation: ...


class IdentifierSource(Protocol):
    def new(self) -> str: ...


def create_topic(name: str) -> LessonTopic:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("lesson topic must not be empty")
    if len(cleaned) > 120:
        raise ValueError("lesson topic is too long")
    return LessonTopic(name=cleaned)


def summarize_topic(topic: LessonTopic) -> TopicSummary:
    ready = [unit for unit in topic.units if unit.material is not None]
    mastery = sum(unit.mastery for unit in ready) / len(ready) if ready else 0.0
    return TopicSummary(
        name=topic.name,
        unit_count=len(ready),
        mastery=round(mastery, 2),
        last_reviewed_at=topic.last_reviewed_at,
    )


class PrepareLesson:
    """Select useful existing units and author missing material."""

    def __init__(
        self,
        author: LessonAuthor,
        *,
        units_per_session: int = 2,
        maximum_units: int = 8,
    ) -> None:
        if units_per_session < 1:
            raise ValueError("units per session must be positive")
        if maximum_units < units_per_session:
            raise ValueError("maximum units must cover one session")
        self._author = author
        self._units_per_session = units_per_session
        self._maximum_units = maximum_units

    async def execute(
        self, topic: LessonTopic, profile: LearnerProfile
    ) -> PreparedLesson:
        units = list(topic.units)
        ready = sorted(
            (unit for unit in units if unit.material is not None),
            key=lambda unit: (
                unit.mastery,
                len(unit.history),
                unit.name.casefold(),
            ),
        )
        selected = ready[: self._units_per_session]
        missing = self._units_per_session - len(selected)

        pending = [unit for unit in units if unit.material is None][:missing]
        if pending:
            all_names = tuple(unit.name for unit in units)
            materials = await asyncio.gather(
                *(
                    self._author.write_material(
                        MaterialRequest(
                            topic=topic.name,
                            unit=unit.name,
                            neighboring_units=all_names,
                            profile=profile,
                        )
                    )
                    for unit in pending
                )
            )
            authored_pending = [
                replace(unit, material=_clean_material(material))
                for unit, material in zip(pending, materials, strict=True)
            ]
            replacements = {unit.name.casefold(): unit for unit in authored_pending}
            units = [replacements.get(unit.name.casefold(), unit) for unit in units]
            selected.extend(authored_pending)
            missing = self._units_per_session - len(selected)

        can_expand = not topic.curriculum_exhausted and len(units) < self._maximum_units
        exhausted = topic.curriculum_exhausted
        if missing and can_expand:
            available_slots = self._maximum_units - len(units)
            requested = min(missing, available_slots)
            proposed = await self._author.propose_units(
                CurriculumRequest(
                    topic=topic.name,
                    existing_units=tuple(unit.name for unit in units),
                    requested_count=requested,
                    profile=profile,
                )
            )
            names = _unique_new_names(proposed, units, requested)
            exhausted = len(names) < requested or len(units) + len(names) >= self._maximum_units
            new_units = [LessonUnit(name=name) for name in names]
            all_names = tuple(unit.name for unit in [*units, *new_units])
            materials = await asyncio.gather(
                *(
                    self._author.write_material(
                        MaterialRequest(
                            topic=topic.name,
                            unit=unit.name,
                            neighboring_units=all_names,
                            profile=profile,
                        )
                    )
                    for unit in new_units
                )
            )
            authored = [
                replace(unit, material=_clean_material(material))
                for unit, material in zip(new_units, materials, strict=True)
            ]
            units.extend(authored)
            selected.extend(authored)

        if not selected:
            raise ValueError("lesson author returned no usable units")

        updated = replace(
            topic,
            units=tuple(units),
            curriculum_exhausted=exhausted,
        )
        return PreparedLesson(updated, tuple(selected[: self._units_per_session]))


class QuestionSchedule:
    def __init__(self, question_count: int = 6) -> None:
        if question_count < 1:
            raise ValueError("question count must be positive")
        self.question_count = question_count

    def arrange(self, units: Sequence[LessonUnit]) -> tuple[str, ...]:
        names = tuple(unit.name for unit in units if unit.material is not None)
        if not names:
            return ()
        return tuple(names[index % len(names)] for index in range(self.question_count))


class BuildLessonQuestion:
    def __init__(self, author: LessonAuthor, identifiers: IdentifierSource) -> None:
        self._author = author
        self._identifiers = identifiers

    async def execute(
        self,
        *,
        topic: str,
        unit: LessonUnit,
        previous_questions: Sequence[str],
        profile: LearnerProfile,
    ) -> LessonQuestion:
        if unit.material is None:
            raise ValueError("cannot ask a question for a unit without material")
        text = (
            await self._author.write_question(
                QuestionRequest(
                    topic=topic,
                    unit=unit,
                    previous_questions=tuple(previous_questions),
                    profile=profile,
                )
            )
        ).strip()
        if not text:
            raise ValueError("lesson author returned an empty question")
        return LessonQuestion(self._identifiers.new(), unit.name, text)


class CheckLessonAnswer:
    def __init__(self, author: LessonAuthor) -> None:
        self._author = author

    async def execute(self, request: AnswerRequest) -> LessonEvaluation:
        answer = request.answer.strip()
        if not answer:
            return LessonEvaluation("garbage", "Please enter an answer.")
        result = await self._author.evaluate_lesson_answer(
            replace(request, answer=answer)
        )
        if result.outcome not in {"correct", "vague", "incorrect", "garbage"}:
            raise ValueError("lesson author returned an invalid outcome")
        feedback = result.feedback.strip()
        if not feedback:
            raise ValueError("lesson author returned empty feedback")
        return LessonEvaluation(result.outcome, feedback)


class RecordLessonResults:
    """Fold session evidence into mastery without replacing prior knowledge."""

    _SCORES: Mapping[LessonOutcome, float] = {
        "correct": 1.0,
        "vague": 0.55,
        "incorrect": 0.0,
        "garbage": 0.0,
    }

    def __init__(self, history_limit: int = 50) -> None:
        if history_limit < 1:
            raise ValueError("history limit must be positive")
        self._history_limit = history_limit

    def execute(
        self,
        topic: LessonTopic,
        answers_by_unit: Mapping[str, Sequence[RecordedAnswer]],
        *,
        reviewed_at: float,
    ) -> LessonTopic:
        folded: list[LessonUnit] = []
        for unit in topic.units:
            answers = [
                item
                for item in answers_by_unit.get(unit.name, ())
                if item.outcome != "garbage"
            ]
            if not answers:
                folded.append(unit)
                continue

            prior_weight = min(6, max(2, len(unit.history)))
            evidence = sum(self._SCORES[item.outcome] for item in answers)
            mastery = (unit.mastery * prior_weight + evidence) / (
                prior_weight + len(answers)
            )
            history = (
                *unit.history,
                *(LessonAttempt(item.question, item.outcome) for item in answers),
            )[-self._history_limit :]
            folded.append(
                replace(
                    unit,
                    mastery=max(0.0, min(1.0, mastery)),
                    history=history,
                )
            )

        return replace(topic, units=tuple(folded), last_reviewed_at=reviewed_at)


def find_unit(topic: LessonTopic, name: str) -> LessonUnit | None:
    key = name.casefold()
    return next((unit for unit in topic.units if unit.name.casefold() == key), None)


def _unique_new_names(
    proposed: Sequence[str], existing: Sequence[LessonUnit], limit: int
) -> list[str]:
    known = {unit.name.casefold() for unit in existing}
    result: list[str] = []
    for raw in proposed:
        name = " ".join(str(raw).split())
        key = name.casefold()
        if not name or len(name) > 120 or key in known:
            continue
        known.add(key)
        result.append(name)
        if len(result) == limit:
            break
    return result


def _clean_material(material: LessonMaterial) -> LessonMaterial:
    title = " ".join(material.title.split())
    intro = material.intro.strip()
    sections: list[LessonSection] = []
    for section in material.sections:
        header = " ".join(section.header.split())
        items = tuple(item.strip() for item in section.items if item.strip())
        text = section.text.strip()
        if not header or (not items and not text):
            continue
        sections.append(
            LessonSection(
                header=header,
                icon=section.icon.strip(),
                items=items,
                text=text,
                highlight=section.highlight,
            )
        )
    if not title or not sections:
        raise ValueError("lesson author returned incomplete material")
    return LessonMaterial(title=title, intro=intro, sections=tuple(sections))
