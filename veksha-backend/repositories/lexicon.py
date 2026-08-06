"""Repository for LexicalItem v2 persistence and review scheduling."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime

import db
import fsrs
from config import (
    FSRS_DESIRED_RETENTION,
    FSRS_MAX_INTERVAL_DAYS,
    FSRS_MIN_INTERVAL_DAYS,
    REVIEW_WINDOW_HOURS,
)
from learning_core_v2.acquisition import (
    LexicalItem,
    ReviewSchedule,
    VocabularyEncounter,
    lexical_item_id,
)
from learning_core_v2.skills import (
    NEUTRAL_CONFIDENCE,
    SKILLS,
    Skill,
    SkillProfile,
    SkillState,
    record_attempt,
)


log = logging.getLogger(__name__)


class LexiconRepository:
    def __init__(self, username: str, items: Iterable[LexicalItem] = ()) -> None:
        self._username = username
        self._items = list(items)

    @classmethod
    def from_document(
        cls,
        username: str,
        document: dict,
        default_language: str = "",
    ) -> tuple["LexiconRepository", bool]:
        migrated = "lexical_items" not in document
        items = (
            _migrate_legacy_items(document, default_language)
            if migrated
            else [
                _item_from_dict(value)
                for value in document.get("lexical_items", [])
                if isinstance(value, dict)
            ]
        )
        return cls(username, items), migrated

    def to_document(self) -> list[dict]:
        return [_item_to_dict(item) for item in self._items]

    def all(self) -> tuple[LexicalItem, ...]:
        return tuple(self._items)

    def find(self, item_id: str) -> LexicalItem | None:
        return next((item for item in self._items if item.item_id == item_id), None)

    def find_active_term(self, term: str, language: str) -> LexicalItem | None:
        key = _normalize(term)
        return next(
            (
                item
                for item in self._items
                if item.language == language
                and _normalize(item.term) == key
                and item.status in {"learning", "known"}
            ),
            None,
        )

    def append(self, item: LexicalItem) -> None:
        if self.find(item.item_id) is not None:
            raise ValueError("lexical item already exists")
        self._items.append(item)

    def extend(self, items: Iterable[LexicalItem]) -> None:
        for item in items:
            self.append(item)

    def replace(self, updated: LexicalItem) -> None:
        index = next(
            (index for index, item in enumerate(self._items) if item.item_id == updated.item_id),
            None,
        )
        if index is None:
            raise ValueError("lexical item not found")
        self._items[index] = updated

    def replace_all(self, items: Iterable[LexicalItem]) -> None:
        values = list(items)
        identifiers = [item.item_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate lexical item id")
        self._items = values

    def remove(self, item_id: str) -> bool:
        item = self.find(item_id)
        if item is None:
            return False
        self._items.remove(item)
        return True

    def pending(self, language: str) -> tuple[LexicalItem, ...]:
        return tuple(
            item
            for item in self._items
            if item.status == "suggested" and item.language == language
        )

    def due_count(self, now: float | None = None) -> int:
        timestamp = time.time() if now is None else now
        return sum(
            1
            for item in self._items
            if item.status == "learning" and _is_due(item, timestamp)
        )

    def learning_count(self) -> int:
        return sum(item.status == "learning" for item in self._items)

    def known_count(self) -> int:
        return sum(item.status == "known" for item in self._items)

    def record_skill_attempt(
        self, item: LexicalItem, skill: Skill, rating_name: str, *, now: float | None = None
    ) -> LexicalItem:
        """Fold one graded answer into the sense's per-skill confidence.

        Corrective tasks call this without touching the FSRS schedule: a repair
        proves something about the skill, not about when the sense is next due.
        """
        if skill not in SKILLS:
            raise ValueError("unknown practice skill")
        timestamp = time.time() if now is None else now
        updated = replace(
            item,
            skills=item.skills.with_state(
                skill,
                record_attempt(item.skills.state(skill), rating_name, now=timestamp),  # type: ignore[arg-type]
            ),
        )
        self.replace(updated)
        return updated

    def apply_review_result(
        self,
        item: LexicalItem,
        outcome: str,
        task_type: str = "",
        *,
        rating_name: str = "",
        skill: Skill | None = None,
    ) -> LexicalItem:
        """Reschedule a sense from one answer.

        `rating_name` carries a graded Again/Hard/Good/Easy when the caller has
        one; surfaces that only know a verdict fall back to mapping `outcome`.
        """
        rating = (
            fsrs.rating_from_name(rating_name)
            if rating_name
            else fsrs.outcome_to_rating(outcome)
        )
        if rating is None:
            return item
        now = time.time()
        if skill is not None:
            item = self.record_skill_attempt(
                item, skill, fsrs.rating_name(rating), now=now
            )
        schedule = item.schedule
        if schedule.stability > 0 and schedule.last_review_at > 0:
            elapsed_days = max(0.0, (now - schedule.last_review_at) / 86400)
            retrievability = fsrs.retrievability(elapsed_days, schedule.stability)
            state = fsrs.review(
                fsrs.MemoryState(schedule.stability, schedule.difficulty),
                rating,
                elapsed_days,
            )
        else:
            elapsed_days = 0.0
            retrievability = None
            state = fsrs.init_state(rating)
        interval_days = min(
            max(
                fsrs.interval_days(state.stability, FSRS_DESIRED_RETENTION),
                FSRS_MIN_INTERVAL_DAYS,
            ),
            FSRS_MAX_INTERVAL_DAYS,
        )
        updated = replace(
            item,
            schedule=ReviewSchedule(
                review_count=max(schedule.review_count + 1, 1),
                next_review_at=now + interval_days * 86400,
                added_at=schedule.added_at,
                delayed=False,
                stability=state.stability,
                difficulty=state.difficulty,
                last_review_at=now,
                lapses=schedule.lapses + (1 if rating == fsrs.AGAIN else 0),
            ),
        )
        self.replace(updated)
        db.review_log_add(
            username=self._username,
            lexical_item_id=item.item_id,
            word=item.term,
            ts=now,
            rating=rating,
            outcome=outcome,
            task_type=task_type,
            elapsed_days=elapsed_days,
            scheduled_days=interval_days,
            stability=updated.schedule.stability,
            difficulty=updated.schedule.difficulty,
            retrievability=retrievability,
        )
        log.info(
            "review stored: user=%r item=%s outcome=%s next=%s",
            self._username,
            item.item_id,
            outcome,
            datetime.fromtimestamp(updated.schedule.next_review_at).isoformat(),
        )
        return updated

    def apply_overdue_decay(self) -> tuple[LexicalItem, ...]:
        now = time.time()
        window_seconds = REVIEW_WINDOW_HOURS * 3600
        affected: list[LexicalItem] = []
        for item in tuple(self._items):
            schedule = item.schedule
            if (
                item.status == "learning"
                and schedule.review_count >= 0
                and not schedule.delayed
                and now - schedule.next_review_at > window_seconds
            ):
                updated = replace(item, schedule=replace(schedule, delayed=True))
                self.replace(updated)
                affected.append(updated)
        return tuple(affected)

    def __len__(self) -> int:
        return len(self._items)


def _item_from_dict(data: dict) -> LexicalItem:
    status = str(data.get("status", "suggested"))
    term = str(data.get("term", ""))
    language = str(data.get("language", ""))
    translation = str(data.get("translation", ""))
    schedule = data.get("schedule") or {}
    return LexicalItem(
        item_id=str(data.get("item_id", "")) or lexical_item_id(term, language, translation),
        term=term,
        language=language,
        translation=translation,
        transcription=str(data.get("transcription", "")),
        status=status if status in {"suggested", "learning", "known", "ignored"} else "suggested",
        encounters=tuple(
            VocabularyEncounter(
                context=str(value.get("context", "")),
                source_url=str(value.get("source_url", "")),
                observed_at=float(value.get("observed_at", 0.0) or 0.0),
            )
            for value in data.get("encounters", [])
            if isinstance(value, dict)
        ),
        schedule=ReviewSchedule(
            review_count=int(schedule.get("review_count", -1)),
            next_review_at=float(schedule.get("next_review_at", 0.0) or 0.0),
            added_at=float(schedule.get("added_at", 0.0) or 0.0),
            delayed=bool(schedule.get("delayed", False)),
            stability=float(schedule.get("stability", 0.0) or 0.0),
            difficulty=float(schedule.get("difficulty", 0.0) or 0.0),
            last_review_at=float(schedule.get("last_review_at", 0.0) or 0.0),
            lapses=max(0, int(schedule.get("lapses", 0) or 0)),
        ),
        skills=_skills_from_dict(data.get("skills")),
        extra_data=str(data.get("extra_data", "")),
        sentence_mining=(
            data.get("sentence_mining")
            if isinstance(data.get("sentence_mining"), dict) and data.get("sentence_mining")
            else None
        ),
    )


def _item_to_dict(item: LexicalItem) -> dict:
    return {
        "item_id": item.item_id,
        "term": item.term,
        "language": item.language,
        "translation": item.translation,
        "transcription": item.transcription,
        "status": item.status,
        "encounters": [
            {
                "context": value.context,
                "source_url": value.source_url,
                "observed_at": value.observed_at,
            }
            for value in item.encounters
        ],
        "schedule": {
            "review_count": item.schedule.review_count,
            "next_review_at": item.schedule.next_review_at,
            "added_at": item.schedule.added_at,
            "delayed": item.schedule.delayed,
            "stability": item.schedule.stability,
            "difficulty": item.schedule.difficulty,
            "last_review_at": item.schedule.last_review_at,
            "lapses": item.schedule.lapses,
        },
        "skills": _skills_to_dict(item.skills),
        "extra_data": item.extra_data,
        "sentence_mining": item.sentence_mining or {},
    }


def _skills_from_dict(data: object) -> SkillProfile:
    """Read a stored skill profile; anything missing starts neutral.

    Senses written before the Adaptive Practice Planner have no `skills` key at
    all, which is exactly the neutral profile — they enter the planner ranked
    by their FSRS schedule instead of as failures.
    """
    if not isinstance(data, dict):
        return SkillProfile()
    profile = SkillProfile()
    for skill in SKILLS:
        state = data.get(skill)
        if not isinstance(state, dict):
            continue
        profile = profile.with_state(
            skill,
            SkillState(
                attempts=max(0, int(state.get("attempts", 0) or 0)),
                errors=max(0, int(state.get("errors", 0) or 0)),
                streak=max(0, int(state.get("streak", 0) or 0)),
                last_practiced_at=float(state.get("last_practiced_at", 0.0) or 0.0),
                confidence=min(
                    1.0,
                    max(0.0, float(state.get("confidence", NEUTRAL_CONFIDENCE))),
                ),
            ),
        )
    return profile


def _skills_to_dict(profile: SkillProfile) -> dict:
    return {
        skill: {
            "attempts": state.attempts,
            "errors": state.errors,
            "streak": state.streak,
            "last_practiced_at": state.last_practiced_at,
            "confidence": state.confidence,
        }
        for skill, state in profile.as_mapping().items()
        if state.attempts > 0
    }


def _legacy_schedule(data: dict, index: int) -> ReviewSchedule:
    return ReviewSchedule(
        review_count=int(data.get("counter", -1)),
        next_review_at=float(data.get("next_review", 0.0) or 0.0),
        added_at=float(data.get("added_at", 0.0) or index + 1),
        delayed=bool(data.get("delayed", False)),
        stability=float(data.get("stability", 0.0) or 0.0),
        difficulty=float(data.get("difficulty", 0.0) or 0.0),
        last_review_at=float(data.get("last_review", 0.0) or 0.0),
        lapses=max(0, int(data.get("lapses", 0) or 0)),
    )


def _migrate_legacy_items(data: dict, default_language: str) -> list[LexicalItem]:
    inbox = [
        _item_from_dict(value)
        for value in data.get("vocabulary_inbox", [])
        if isinstance(value, dict)
    ]
    words = [value for value in data.get("words", []) if isinstance(value, dict)]
    matched: set[int] = set()
    migrated: list[LexicalItem] = []
    for item in inbox:
        match = next(
            (
                (index, word)
                for index, word in enumerate(words)
                if _normalize(str(word.get("name", ""))) == _normalize(item.term)
                and (str(word.get("language", "")) or default_language).lower().replace("_", "-")
                == item.language.lower().replace("_", "-")
            ),
            None,
        )
        if match is None or item.status not in {"learning", "known"}:
            migrated.append(item)
            continue
        index, word = match
        matched.add(index)
        context = str(word.get("context", ""))
        encounters = item.encounters or (
            (VocabularyEncounter(context=context, observed_at=float(word.get("added_at", 0.0) or index + 1)),)
            if context
            else ()
        )
        migrated.append(
            replace(
                item,
                schedule=_legacy_schedule(word, index),
                encounters=encounters,
                extra_data=str(word.get("extra_data", "")),
                sentence_mining=word.get("sentence_mining") or None,
            )
        )
    for index, word in enumerate(words):
        if index in matched:
            continue
        term = str(word.get("name", ""))
        language = str(word.get("language", "")) or default_language
        translation = str(word.get("translation", ""))
        context = str(word.get("context", ""))
        migrated.append(
            LexicalItem(
                item_id=lexical_item_id(term, language, translation),
                term=term,
                language=language,
                translation=translation,
                transcription=str(word.get("transcription", "")),
                status="known" if bool(word.get("known", False)) else "learning",
                encounters=(
                    (VocabularyEncounter(context=context, observed_at=float(word.get("added_at", 0.0) or index + 1)),)
                    if context
                    else ()
                ),
                schedule=_legacy_schedule(word, index),
                extra_data=str(word.get("extra_data", "")),
                sentence_mining=word.get("sentence_mining") or None,
            )
        )
    return migrated


def _is_due(item: LexicalItem, now: float) -> bool:
    return (
        item.schedule.review_count >= 0
        and item.schedule.next_review_at - now <= REVIEW_WINDOW_HOURS * 3600
    )


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())
