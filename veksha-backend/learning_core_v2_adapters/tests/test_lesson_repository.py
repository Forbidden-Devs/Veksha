from __future__ import annotations

import json

from learning_core_v2.lesson import (
    LessonAttempt,
    LessonMaterial,
    LessonSection,
    LessonTopic,
    LessonUnit,
)
from models import LessonBlock, LessonQA, LessonTopic as StoredTopic
from repositories.lessons import LessonRepository


def test_repository_reads_existing_lesson_documents():
    content = {
        "title": "Introductions",
        "intro": "Start a conversation.",
        "sections": [{"header": "Pattern", "items": ["Hello, I am …"], "highlight": True}],
    }
    repository = LessonRepository.from_document(
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
            ).to_dict()
        ]
    )

    topic = repository.find(" small talk ")

    assert topic is not None
    assert topic.units[0].material is not None
    assert topic.units[0].material.sections[0].highlight is True
    assert topic.units[0].history[0].outcome == "correct"


def test_repository_round_trips_new_domain_and_replaces_existing_topic():
    repository = LessonRepository.from_document([StoredTopic("Small talk").to_dict()])
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

    repository.put(topic)

    assert len(repository) == 1
    assert LessonRepository.from_document(repository.to_document()).find("Small talk") == topic


def test_repository_creates_normalized_topic_once():
    repository = LessonRepository()

    first = repository.get_or_create("  Business   English ")
    second = repository.get_or_create("business english")

    assert first.name == "Business English"
    assert second.name == "Business English"
    assert len(repository) == 1
