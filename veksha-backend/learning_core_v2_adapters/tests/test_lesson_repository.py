from __future__ import annotations

import json
from dataclasses import dataclass, field

from learning_core_v2.lesson import (
    LessonAttempt,
    LessonMaterial,
    LessonSection,
    LessonTopic,
    LessonUnit,
)
from learning_core_v2_adapters.lesson import UserStorageLessonRepository
from models import LessonBlock, LessonQA, LessonTopic as StoredTopic


@dataclass
class FakeStorage:
    lesson_topics: list[StoredTopic] = field(default_factory=list)
    saves: int = 0

    def find_lesson_topic(self, name):
        key = name.strip().casefold()
        return next(
            (topic for topic in self.lesson_topics if topic.name.casefold() == key),
            None,
        )

    def save(self):
        self.saves += 1


def test_repository_reads_existing_lesson_documents():
    content = {
        "title": "Introductions",
        "intro": "Start a conversation.",
        "sections": [
            {
                "header": "Pattern",
                "items": ["Hello, I am …"],
                "highlight": True,
            }
        ],
    }
    storage = FakeStorage(
        [
            StoredTopic(
                "Small talk",
                blocks=[
                    LessonBlock(
                        "Introductions",
                        json.dumps(content),
                        0.75,
                        [LessonQA("How do you introduce yourself?", "correct")],
                    )
                ],
            )
        ]
    )

    topic = UserStorageLessonRepository(storage).find(" small talk ")

    assert topic is not None
    assert topic.units[0].material is not None
    assert topic.units[0].material.sections[0].highlight is True
    assert topic.units[0].history[0].outcome == "correct"


def test_repository_round_trips_new_domain_and_replaces_existing_topic():
    storage = FakeStorage([StoredTopic("Small talk")])
    repository = UserStorageLessonRepository(storage)
    topic = LessonTopic(
        "Small talk",
        units=(
            LessonUnit(
                "Introductions",
                LessonMaterial(
                    "Introductions",
                    "Start here.",
                    (LessonSection("Pattern", items=("Hello!",)),),
                ),
                0.6,
                (LessonAttempt("Say hello", "vague"),),
            ),
        ),
        curriculum_exhausted=True,
        last_reviewed_at=123.0,
    )

    repository.save(topic)

    assert storage.saves == 1
    assert len(storage.lesson_topics) == 1
    restored = repository.find("Small talk")
    assert restored == topic


def test_repository_creates_normalized_topic_once():
    storage = FakeStorage()
    repository = UserStorageLessonRepository(storage)

    first = repository.get_or_create("  Business   English ")
    second = repository.get_or_create("business english")

    assert first.name == "Business English"
    assert second.name == "Business English"
    assert len(storage.lesson_topics) == 1
    assert storage.saves == 1
