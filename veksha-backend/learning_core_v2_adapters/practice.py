"""Adapters between core-v2 practice concepts and Veksha infrastructure."""

from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import TypeVar

from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.practice import AnswerEvaluation, TaskKind
from storage import UserStorage


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


class UserStoragePracticeRepository:
    def __init__(self, storage: UserStorage) -> None:
        self._storage = storage

    def items(self) -> tuple[LexicalItem, ...]:
        return tuple(self._storage.lexical_items)

    def contains(self, item_id: str) -> bool:
        return self._storage.find_lexical_item(item_id) is not None

    def mark_known(self, item_id: str) -> bool:
        item = self._storage.find_lexical_item(item_id)
        if item is None:
            return False
        self._storage.replace_lexical_item(
            replace(
                item,
                status="known",
                schedule=replace(item.schedule, delayed=False),
            )
        )
        self._storage.save()
        return True

    def apply_evaluation(
        self,
        item_id: str,
        evaluation: AnswerEvaluation,
        task_kind: TaskKind,
    ) -> bool:
        if not evaluation.should_update_schedule:
            return False
        item = self._storage.find_lexical_item(item_id)
        if item is None:
            return False
        self._storage.apply_review_result(
            item, evaluation.outcome, task_type=task_kind
        )
        self._storage.save()
        return True
