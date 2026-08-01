from dataclasses import dataclass, field

from learning_core_v2.acquisition import LexicalItem, ReviewSchedule
from learning_core_v2.practice import AnswerEvaluation
from learning_core_v2_adapters.practice import LexiconPracticeRepository
from repositories.lexicon import LexiconRepository


def lexical_item() -> LexicalItem:
    return LexicalItem(
        item_id="sense-run",
        term="run",
        language="en",
        translation="бежать",
        status="learning",
        schedule=ReviewSchedule(review_count=2, next_review_at=100, delayed=True),
    )


class RecordingLexicon(LexiconRepository):
    def __init__(self):
        super().__init__("tester", [lexical_item()])
        self.reviews = []

    def apply_review_result(self, item, outcome, task_type=""):
        self.reviews.append((item.item_id, outcome, task_type))


@dataclass
class FakeStorage:
    lexicon: RecordingLexicon = field(default_factory=RecordingLexicon)
    saves: int = 0

    def save(self):
        self.saves += 1


def test_repository_exposes_lexical_items_without_legacy_projection():
    storage = FakeStorage()
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)

    result = repository.items()

    assert result[0] is storage.lexicon.all()[0]
    assert result[0].item_id == "sense-run"


def test_repository_applies_only_schedulable_evaluations_by_item_id():
    storage = FakeStorage()
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)

    assert repository.apply_evaluation(
        "sense-run", AnswerEvaluation("correct", "ok"), "translation"
    )
    assert not repository.apply_evaluation(
        "sense-run", AnswerEvaluation("garbage", "retry"), "translation"
    )

    assert storage.lexicon.reviews == [("sense-run", "correct", "translation")]
    assert storage.saves == 1


def test_mark_known_updates_only_selected_sense():
    storage = FakeStorage()
    storage.lexicon.append(
        LexicalItem("sense-run-noun", "run", "en", "забег", status="learning")
    )
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)

    assert repository.mark_known("sense-run")

    assert storage.lexicon.all()[0].status == "known"
    assert storage.lexicon.all()[0].schedule.delayed is False
    assert storage.lexicon.all()[1].status == "learning"
    assert storage.saves == 1
