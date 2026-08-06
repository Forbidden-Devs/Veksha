from dataclasses import dataclass, field, replace

from learning_core_v2.acquisition import LexicalItem, ReviewSchedule
from learning_core_v2.practice import GradedAnswer, PlanReason, PracticeTask
from learning_core_v2.skills import SkillProfile
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


def task(stage="core", skill="recall", kind="reverse_translation") -> PracticeTask:
    return PracticeTask(
        task_id="task-1",
        item_id="sense-run",
        word="run",
        context="",
        kind=kind,
        skill=skill,
        stage=stage,
        question="Назовите слово",
        review_count=2,
        reason=PlanReason("weakest_skill", skill),
    )


def graded(rating, *, stage="core") -> GradedAnswer:
    return GradedAnswer(
        task=task(stage=stage),
        outcome="correct" if rating != "again" else "incorrect",
        feedback="ok",
        error_note="",
        rating=rating,
        suggested_rating=rating,
        manual_rating=False,
        counts_as_review=stage == "core",
        correction=None,
        profile=SkillProfile(),
    )


class RecordingLexicon(LexiconRepository):
    def __init__(self):
        super().__init__("tester", [lexical_item()])
        self.reviews = []
        self.skill_attempts = []

    def apply_review_result(
        self, item, outcome, task_type="", *, rating_name="", skill=None
    ):
        self.reviews.append((item.item_id, outcome, task_type, rating_name, skill))
        return item

    def record_skill_attempt(self, item, skill, rating_name, *, now=None):
        self.skill_attempts.append((item.item_id, skill, rating_name))
        return item


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


def test_planned_answer_reschedules_with_its_graded_rating_and_skill():
    storage = FakeStorage()
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)

    assert repository.apply_grade(graded("easy"))

    assert storage.lexicon.reviews == [
        ("sense-run", "correct", "reverse_translation", "easy", "recall")
    ]
    assert storage.saves == 1


def test_corrective_answer_moves_the_skill_without_touching_the_schedule():
    storage = FakeStorage()
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)

    assert repository.apply_grade(graded("good", stage="support"))

    assert storage.lexicon.reviews == []
    assert storage.lexicon.skill_attempts == [("sense-run", "recall", "good")]


def test_a_non_answer_changes_nothing():
    storage = FakeStorage()
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)

    assert not repository.apply_grade(replace(graded("good"), rating=None))

    assert storage.lexicon.reviews == []
    assert storage.lexicon.skill_attempts == []
    assert storage.saves == 0


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


def test_skill_profiles_survive_a_document_round_trip():
    source = LexiconRepository("tester", [lexical_item()])
    item = source.all()[0]
    source.replace(
        replace(item, skills=item.skills.record("listening", "hard", now=1_700.0))
    )

    restored, _ = LexiconRepository.from_document(
        "tester", {"lexical_items": source.to_document()}
    )

    state = restored.all()[0].skills.state("listening")
    assert state.attempts == 1
    assert state.last_practiced_at == 1_700.0
    assert 0.0 < state.confidence < 0.5


def test_senses_stored_before_the_planner_load_with_a_neutral_profile():
    restored, _ = LexiconRepository.from_document(
        "tester",
        {
            "lexical_items": [
                {
                    "item_id": "sense-run",
                    "term": "run",
                    "language": "en",
                    "translation": "бежать",
                    "status": "learning",
                }
            ]
        },
    )

    profile = restored.all()[0].skills
    assert profile.entries == ()
    assert profile.state("recall").confidence == 0.5
    assert profile.state("recall").attempts == 0
