from __future__ import annotations

from dataclasses import dataclass, field

from learning_core_v2.practice import AnswerEvaluation
from learning_core_v2_adapters.practice import UserStoragePracticeRepository


@dataclass
class FakeWord:
    name: str = "run"
    language: str = "en"
    context: str = "I run"
    translation: str = "бежать"
    counter: int = 2
    next_review: float = 100
    added_at: float = 10
    known: bool = False
    delayed: bool = True


@dataclass
class FakeStorage:
    words: list[FakeWord] = field(default_factory=lambda: [FakeWord()])
    reviews: list = field(default_factory=list)
    saves: int = 0

    def find_word(self, name):
        return next((word for word in self.words if word.name == name), None)

    def apply_review_result(self, word, outcome, task_type=""):
        self.reviews.append((word.name, outcome, task_type))

    def save(self):
        self.saves += 1


def test_repository_maps_storage_without_exposing_it_to_core():
    repository = UserStoragePracticeRepository(FakeStorage())

    result = repository.words()

    assert result[0].text == "run"
    assert result[0].review_count == 2
    assert result[0].translation == "бежать"


def test_repository_applies_only_schedulable_evaluations():
    storage = FakeStorage()
    repository = UserStoragePracticeRepository(storage)

    assert repository.apply_evaluation(
        "run", AnswerEvaluation("correct", "ok"), "translation"
    )
    assert not repository.apply_evaluation(
        "run", AnswerEvaluation("garbage", "retry"), "translation"
    )

    assert storage.reviews == [("run", "correct", "translation")]
    assert storage.saves == 1


def test_mark_known_clears_delay_and_persists():
    storage = FakeStorage()
    repository = UserStoragePracticeRepository(storage)

    assert repository.mark_known("run")

    assert storage.words[0].known is True
    assert storage.words[0].delayed is False
    assert storage.saves == 1
