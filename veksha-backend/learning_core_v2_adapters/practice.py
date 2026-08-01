"""Adapters between core-v2 practice concepts and Veksha infrastructure."""

from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import Callable, TypeVar

from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.practice import AnswerEvaluation, TaskKind
from repositories.lexicon import LexiconRepository


T = TypeVar("T")


class RandomChoiceSource:
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

    def apply_evaluation(
        self,
        item_id: str,
        evaluation: AnswerEvaluation,
        task_kind: TaskKind,
    ) -> bool:
        if not evaluation.should_update_schedule:
            return False
        item = self._lexicon.find(item_id)
        if item is None:
            return False
        self._lexicon.apply_review_result(
            item, evaluation.outcome, task_type=task_kind
        )
        self._commit()
        return True
