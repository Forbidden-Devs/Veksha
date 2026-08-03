"""Repository and persistence mapping for lesson core v2."""

from __future__ import annotations

import json
from collections.abc import Iterable
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


_OUTCOMES = {"correct", "vague", "incorrect", "garbage"}


class LessonRepository:
    def __init__(self, topics: Iterable[LessonTopic] = ()) -> None:
        self._topics = list(topics)

    @classmethod
    def from_document(cls, values: object) -> "LessonRepository":
        if not isinstance(values, list):
            return cls()
        return cls(
            _to_domain(StoredTopic.from_dict(value))
            for value in values
            if isinstance(value, dict)
        )

    def to_document(self) -> list[dict]:
        return [_to_storage(topic).to_dict() for topic in self._topics]

    def topics(self) -> tuple[LessonTopic, ...]:
        return tuple(self._topics)

    def find(self, name: str) -> LessonTopic | None:
        key = _normalize(name)
        return next((topic for topic in self._topics if _normalize(topic.name) == key), None)

    def get_or_create(self, name: str) -> LessonTopic:
        existing = self.find(name)
        if existing is not None:
            return existing
        topic = create_topic(name)
        self.put(topic)
        return topic

    def put(self, topic: LessonTopic) -> None:
        current = self.find(topic.name)
        if current is None:
            self._topics.append(topic)
        else:
            self._topics[self._topics.index(current)] = topic

    def remove(self, name: str) -> bool:
        topic = self.find(name)
        if topic is None:
            return False
        self._topics.remove(topic)
        return True

    def __len__(self) -> int:
        return len(self._topics)


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


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _to_domain(topic: StoredTopic) -> LessonTopic:
    return LessonTopic(
        name=topic.name,
        units=tuple(_unit_to_domain(block) for block in topic.blocks),
        curriculum_exhausted=bool(topic.is_complete),
        last_reviewed_at=topic.last_reviewed,
    )


def _unit_to_domain(block: StoredBlock) -> LessonUnit:
    attempts = tuple(
        LessonAttempt(item.question, item.outcome)
        for item in block.history
        if item.outcome in _OUTCOMES and item.question.strip()
    )
    return LessonUnit(
        name=block.name,
        material=_parse_material(block.content_json),
        mastery=max(0.0, min(1.0, float(block.mastery_score))),
        history=attempts,
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
    sections_data = data.get("sections")
    if not isinstance(title, str) or not title.strip() or not isinstance(sections_data, list):
        return None
    sections = tuple(
        LessonSection(
            header=value["header"],
            icon=str(value.get("icon") or ""),
            items=(
                tuple(str(item) for item in value.get("items", []))
                if isinstance(value.get("items"), list)
                else ()
            ),
            text=str(value.get("text") or ""),
            highlight=bool(value.get("highlight", False)),
        )
        for value in sections_data
        if isinstance(value, dict) and isinstance(value.get("header"), str)
    )
    if not sections:
        return None
    return LessonMaterial(
        title=title,
        intro=str(data.get("intro") or ""),
        sections=sections,
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
