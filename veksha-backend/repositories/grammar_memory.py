"""Repository for persisted Pattern Workshop items."""

from __future__ import annotations

from collections.abc import Iterable

from learning_core_v2.grammar_memory import GrammarEncounter, GrammarMemoryItem


class GrammarMemoryRepository:
    def __init__(self, items: Iterable[GrammarMemoryItem] = ()) -> None:
        self._items = list(items)

    @classmethod
    def from_document(cls, values: object) -> "GrammarMemoryRepository":
        if not isinstance(values, list):
            return cls()
        return cls(_item_from_dict(value) for value in values if isinstance(value, dict))

    def to_document(self) -> list[dict]:
        return [_item_to_dict(item) for item in self._items]

    def all(self) -> tuple[GrammarMemoryItem, ...]:
        return tuple(self._items)

    def for_language(self, language: str) -> tuple[GrammarMemoryItem, ...]:
        return tuple(item for item in self._items if item.language == language)

    def find(self, item_id: str) -> GrammarMemoryItem | None:
        return next((item for item in self._items if item.item_id == item_id), None)

    def replace(self, updated: GrammarMemoryItem) -> None:
        index = next(
            (index for index, item in enumerate(self._items) if item.item_id == updated.item_id),
            None,
        )
        if index is None:
            raise ValueError("pattern skill not found")
        self._items[index] = updated

    def replace_all(self, items: Iterable[GrammarMemoryItem]) -> None:
        self._items = list(items)

    def __len__(self) -> int:
        return len(self._items)


def _item_from_dict(data: dict) -> GrammarMemoryItem:
    status = str(data.get("status", "learning"))
    return GrammarMemoryItem(
        item_id=str(data.get("item_id", "")),
        language=str(data.get("language", "")),
        category=str(data.get("category", "")),
        label=str(data.get("label", "")),
        explanation=str(data.get("explanation", "")),
        status=status if status in {"learning", "mastered"} else "learning",
        seen_count=max(1, int(data.get("seen_count", 1) or 1)),
        first_seen_at=float(data.get("first_seen_at", 0.0) or 0.0),
        last_seen_at=float(data.get("last_seen_at", 0.0) or 0.0),
        encounters=tuple(
            GrammarEncounter(
                example=str(encounter.get("example", "")),
                source_url=str(encounter.get("source_url", "")),
                observed_at=float(encounter.get("observed_at", 0.0) or 0.0),
            )
            for encounter in data.get("encounters", [])
            if isinstance(encounter, dict)
        ),
    )


def _item_to_dict(item: GrammarMemoryItem) -> dict:
    return {
        "item_id": item.item_id,
        "language": item.language,
        "category": item.category,
        "label": item.label,
        "explanation": item.explanation,
        "status": item.status,
        "seen_count": item.seen_count,
        "first_seen_at": item.first_seen_at,
        "last_seen_at": item.last_seen_at,
        "encounters": [
            {
                "example": encounter.example,
                "source_url": encounter.source_url,
                "observed_at": encounter.observed_at,
            }
            for encounter in item.encounters
        ],
    }
