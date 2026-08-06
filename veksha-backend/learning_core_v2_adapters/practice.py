"""Adapters between core-v2 practice concepts and Veksha infrastructure."""

from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import Callable, TypeVar

from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.practice import GradedAnswer
from repositories.lexicon import LexiconRepository


T = TypeVar("T")


class RandomChoiceSource:
    """Tie-breaker for equally rested task formats.

    The planner narrows the field first; randomness only decides between kinds
    the session has used equally often, so no exercise type is picked blindly.
    """

    def __init__(self) -> None:
        self._random = random.SystemRandom()

    def choose(self, values: Sequence[T]) -> T:
        if not values:
            raise ValueError("cannot choose from an empty sequence")
        return self._random.choice(values)


class UuidIdentifierSource:
    def new(self) -> str:
        return str(uuid.uuid4())


class LexiconPracticeRepository:
    def __init__(
        self,
        lexicon: LexiconRepository,
        commit: Callable[[], None],
    ) -> None:
        self._lexicon = lexicon
        self._commit = commit

    def items(self) -> tuple[LexicalItem, ...]:
        return self._lexicon.all()

    def find(self, item_id: str) -> LexicalItem | None:
        return self._lexicon.find(item_id)

    def contains(self, item_id: str) -> bool:
        return self._lexicon.find(item_id) is not None

    def mark_known(self, item_id: str) -> bool:
        item = self._lexicon.find(item_id)
        if item is None:
            return False
        self._lexicon.replace(
            replace(
                item,
                status="known",
                schedule=replace(item.schedule, delayed=False),
            )
        )
        self._commit()
        return True

    def apply_grade(self, graded: GradedAnswer) -> bool:
        """Persist one graded answer.

        A planned task reschedules the sense through FSRS and updates the skill
        it trained. A corrective task only moves the skill: the repair follows
        the same review it was triggered by, and rescheduling twice for one
        lapse would distort the interval.
        """
        if graded.rating is None:
            return False
        item = self._lexicon.find(graded.task.item_id)
        if item is None:
            return False
        if graded.counts_as_review:
            self._lexicon.apply_review_result(
                item,
                graded.outcome,
                task_type=graded.task.kind,
                rating_name=graded.rating,
                skill=graded.task.skill,
            )
        else:
            self._lexicon.record_skill_attempt(item, graded.task.skill, graded.rating)
        self._commit()
        return True
