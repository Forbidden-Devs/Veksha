"""Persistence mapping between lesson core v2 and the existing user document."""

from __future__ import annotations

import json
from typing import Any

from learning_core_v2.lesson import (
    LessonAttempt,
    LessonMaterial,
    LessonSection,
    LessonTopic,
    LessonUnit,
    create_topic,
)
from models import LessonBlock as StoredBlock
from models import LessonQA as StoredAttempt
from models import LessonTopic as StoredTopic
from storage import UserStorage


_OUTCOMES = {"correct", "vague", "incorrect", "garbage"}


class UserStorageLessonRepository:
    def __init__(self, storage: UserStorage) -> None:
        self._storage = storage

    def topics(self) -> tuple[LessonTopic, ...]:
        return tuple(_to_domain(topic) for topic in self._storage.lesson_topics)

    def find(self, name: str) -> LessonTopic | None:
        stored = self._storage.find_lesson_topic(name)
        return _to_domain(stored) if stored is not None else None

    def get_or_create(self, name: str) -> LessonTopic:
        existing = self.find(name)
        if existing is not None:
            return existing
        topic = create_topic(name)
        self.save(topic)
        return topic

    def save(self, topic: LessonTopic) -> None:
        stored = _to_storage(topic)
        current = self._storage.find_lesson_topic(topic.name)
        if current is None:
            self._storage.lesson_topics.append(stored)
        else:
            index = self._storage.lesson_topics.index(current)
            self._storage.lesson_topics[index] = stored
        self._storage.save()


def material_to_dict(material: LessonMaterial) -> dict[str, Any]:
    return {
        "title": material.title,
        "intro": material.intro,
        "sections": [
            {
                "icon": section.icon,
                "header": section.header,
                "items": list(section.items),
                "text": section.text,
                "highlight": section.highlight,
            }
            for section in material.sections
        ],
    }


def _to_domain(topic: StoredTopic) -> LessonTopic:
    return LessonTopic(
        name=topic.name,
        units=tuple(_unit_to_domain(block) for block in topic.blocks),
        curriculum_exhausted=bool(topic.is_complete),
        last_reviewed_at=topic.last_reviewed,
    )


def _unit_to_domain(block: StoredBlock) -> LessonUnit:
    attempts = []
    for item in block.history:
        if item.outcome in _OUTCOMES and item.question.strip():
            attempts.append(LessonAttempt(item.question, item.outcome))
    return LessonUnit(
        name=block.name,
        material=_parse_material(block.content_json),
        mastery=max(0.0, min(1.0, float(block.mastery_score))),
        history=tuple(attempts),
    )


def _parse_material(raw: str) -> LessonMaterial | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("__skipped__"):
        return None
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    sections_data = data.get("sections")
    if not isinstance(sections_data, list):
        return None
    sections: list[LessonSection] = []
    for value in sections_data:
        if not isinstance(value, dict) or not isinstance(value.get("header"), str):
            continue
        raw_items = value.get("items")
        items = (
            tuple(str(item) for item in raw_items)
            if isinstance(raw_items, list)
            else ()
        )
        sections.append(
            LessonSection(
                header=value["header"],
                icon=str(value.get("icon") or ""),
                items=items,
                text=str(value.get("text") or ""),
                highlight=bool(value.get("highlight", False)),
            )
        )
    if not sections:
        return None
    return LessonMaterial(
        title=title,
        intro=str(data.get("intro") or ""),
        sections=tuple(sections),
    )


def _to_storage(topic: LessonTopic) -> StoredTopic:
    return StoredTopic(
        name=topic.name,
        blocks=[
            StoredBlock(
                name=unit.name,
                content_json=(
                    json.dumps(material_to_dict(unit.material), ensure_ascii=False)
                    if unit.material is not None
                    else ""
                ),
                mastery_score=unit.mastery,
                history=[
                    StoredAttempt(question=item.question, outcome=item.outcome)
                    for item in unit.history
                ],
            )
            for unit in topic.units
        ],
        is_complete=topic.curriculum_exhausted,
        last_reviewed=topic.last_reviewed_at,
    )
