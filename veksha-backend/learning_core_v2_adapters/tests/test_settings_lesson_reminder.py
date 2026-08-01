from __future__ import annotations

import json
from dataclasses import dataclass

from api.settings import _topic_needing_review
from models import LessonBlock, LessonTopic
from repositories.lessons import LessonRepository


@dataclass
class FakeStorage:
    lessons: LessonRepository


def test_topic_reminder_uses_new_domain_policy_for_stored_topics():
    content = json.dumps(
        {
            "title": "Greetings",
            "intro": "Start here.",
            "sections": [{"header": "Pattern", "text": "Hello!"}],
        }
    )
    storage = FakeStorage(
        LessonRepository.from_document([
            LessonTopic(
                "Small talk",
                blocks=[LessonBlock("Greetings", content, mastery_score=0.4)],
            ).to_dict()
        ])
    )

    assert _topic_needing_review(storage) == "Small talk"
