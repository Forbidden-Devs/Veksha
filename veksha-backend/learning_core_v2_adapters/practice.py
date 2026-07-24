"""Adapters between core-v2 practice concepts and Veksha infrastructure."""

from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from typing import TypeVar

from learning_core_v2.practice import AnswerEvaluation, PracticeWord, TaskKind
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

    def words(self) -> list[PracticeWord]:
        return [
            PracticeWord(
                text=word.name,
                language=word.language,
                context=word.context,
                translation=word.translation,
                review_count=word.counter,
                next_review_at=word.next_review,
                added_at=word.added_at,
                known=bool(word.known),
            )
            for word in self._storage.words
        ]

    def contains(self, word_text: str) -> bool:
        return self._storage.find_word(word_text) is not None

    def mark_known(self, word_text: str) -> bool:
        word = self._storage.find_word(word_text)
        if word is None:
            return False
        word.known = True
        word.delayed = False
        self._storage.save()
        return True

    def apply_evaluation(
        self,
        word_text: str,
        evaluation: AnswerEvaluation,
        task_kind: TaskKind,
    ) -> bool:
        if not evaluation.should_update_schedule:
            return False
        word = self._storage.find_word(word_text)
        if word is None:
            return False
        self._storage.apply_review_result(word, evaluation.outcome, task_type=task_kind)
        self._storage.save()
        return True
