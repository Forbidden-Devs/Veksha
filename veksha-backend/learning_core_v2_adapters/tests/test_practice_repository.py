from dataclasses import dataclass, field

from learning_core_v2.acquisition import LexicalItem, ReviewSchedule
from learning_core_v2.practice import AnswerEvaluation
from learning_core_v2_adapters.practice import UserStoragePracticeRepository


def lexical_item() -> LexicalItem:
    return LexicalItem(
        item_id="sense-run",
        term="run",
        language="en",
        translation="бежать",
        status="learning",
        schedule=ReviewSchedule(review_count=2, next_review_at=100, delayed=True),
    )


@dataclass
class FakeStorage:
    lexical_items: list[LexicalItem] = field(default_factory=lambda: [lexical_item()])
    reviews: list = field(default_factory=list)
    saves: int = 0

    def find_lexical_item(self, item_id):
        return next(
            (item for item in self.lexical_items if item.item_id == item_id), None
        )

    def replace_lexical_item(self, updated):
        index = next(
            index
            for index, item in enumerate(self.lexical_items)
            if item.item_id == updated.item_id
        )
        self.lexical_items[index] = updated

    def apply_review_result(self, item, outcome, task_type=""):
        self.reviews.append((item.item_id, outcome, task_type))

    def save(self):
        self.saves += 1


def test_repository_exposes_lexical_items_without_legacy_projection():
    storage = FakeStorage()
    repository = UserStoragePracticeRepository(storage)

    result = repository.items()

    assert result[0] is storage.lexical_items[0]
    assert result[0].item_id == "sense-run"


def test_repository_applies_only_schedulable_evaluations_by_item_id():
    storage = FakeStorage()
    repository = UserStoragePracticeRepository(storage)

    assert repository.apply_evaluation(
        "sense-run", AnswerEvaluation("correct", "ok"), "translation"
    )
    assert not repository.apply_evaluation(
        "sense-run", AnswerEvaluation("garbage", "retry"), "translation"
    )

    assert storage.reviews == [("sense-run", "correct", "translation")]
    assert storage.saves == 1


def test_mark_known_updates_only_selected_sense():
    storage = FakeStorage()
    storage.lexical_items.append(
        LexicalItem("sense-run-noun", "run", "en", "забег", status="learning")
    )
    repository = UserStoragePracticeRepository(storage)

    assert repository.mark_known("sense-run")

    assert storage.lexical_items[0].status == "known"
    assert storage.lexical_items[0].schedule.delayed is False
    assert storage.lexical_items[1].status == "learning"
    assert storage.saves == 1
