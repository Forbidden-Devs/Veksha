"""
storage.py — user Knowledge Base storage.

The KB (words, lesson topics, settings) is persisted as one JSON document per
user in PostgreSQL (see db.py); this module keeps the in-memory object model and
the spaced-repetition primitives on top of it.

Implements:
  - apply_kb_changes — apply {type, value} patches to KB
  - collect_train_word — deterministic word selection for training
  - helper methods for LLM candidate matching (delete_word / delete_topic)
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional

import db
import fsrs
from config import (
    FIRST_REVIEW_DELAY_DAYS,
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
from learning_core_v2.grammar_memory import GrammarEncounter, GrammarMemoryItem
from models import LessonTopic, Patch, UserSettings

log = logging.getLogger(__name__)


def _lexical_item_from_dict(data: dict) -> LexicalItem:
    status = str(data.get("status", "suggested"))
    term = str(data.get("term", ""))
    language = str(data.get("language", ""))
    translation = str(data.get("translation", ""))
    schedule_data = data.get("schedule") or {}
    return LexicalItem(
        item_id=str(data.get("item_id", ""))
        or lexical_item_id(term, language, translation),
        term=term,
        language=language,
        translation=translation,
        transcription=str(data.get("transcription", "")),
        status=status if status in {"suggested", "learning", "known", "ignored"} else "suggested",
        encounters=tuple(
            VocabularyEncounter(
                context=str(encounter.get("context", "")),
                source_url=str(encounter.get("source_url", "")),
                observed_at=float(encounter.get("observed_at", 0.0) or 0.0),
            )
            for encounter in data.get("encounters", [])
            if isinstance(encounter, dict)
        ),
        schedule=ReviewSchedule(
            review_count=int(schedule_data.get("review_count", -1)),
            next_review_at=float(schedule_data.get("next_review_at", 0.0) or 0.0),
            added_at=float(schedule_data.get("added_at", 0.0) or 0.0),
            delayed=bool(schedule_data.get("delayed", False)),
            stability=float(schedule_data.get("stability", 0.0) or 0.0),
            difficulty=float(schedule_data.get("difficulty", 0.0) or 0.0),
            last_review_at=float(schedule_data.get("last_review_at", 0.0) or 0.0),
            lapses=max(0, int(schedule_data.get("lapses", 0) or 0)),
        ),
        extra_data=str(data.get("extra_data", "")),
        sentence_mining=(
            data.get("sentence_mining")
            if isinstance(data.get("sentence_mining"), dict)
            and data.get("sentence_mining")
            else None
        ),
    )


def _lexical_item_to_dict(item: LexicalItem) -> dict:
    return {
        "item_id": item.item_id,
        "term": item.term,
        "language": item.language,
        "translation": item.translation,
        "transcription": item.transcription,
        "status": item.status,
        "encounters": [
            {
                "context": encounter.context,
                "source_url": encounter.source_url,
                "observed_at": encounter.observed_at,
            }
            for encounter in item.encounters
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
        "extra_data": item.extra_data,
        "sentence_mining": item.sentence_mining or {},
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


def _migrate_legacy_lexical_items(
    data: dict, default_language: str = ""
) -> list[LexicalItem]:
    inbox = [
        _lexical_item_from_dict(item)
        for item in data.get("vocabulary_inbox", [])
        if isinstance(item, dict)
    ]
    words = [item for item in data.get("words", []) if isinstance(item, dict)]
    matched_words: set[int] = set()
    migrated: list[LexicalItem] = []

    for item in inbox:
        match = next(
            (
                (index, word)
                for index, word in enumerate(words)
                if _normalize(str(word.get("name", ""))) == _normalize(item.term)
                and (
                    str(word.get("language", "")) or default_language
                ).lower().replace("_", "-")
                == item.language.lower().replace("_", "-")
            ),
            None,
        )
        if match is None or item.status not in {"learning", "known"}:
            migrated.append(item)
            continue
        index, word = match
        matched_words.add(index)
        encounters = item.encounters
        context = str(word.get("context", ""))
        if context and not encounters:
            encounters = (
                VocabularyEncounter(
                    context=context,
                    observed_at=float(word.get("added_at", 0.0) or index + 1),
                ),
            )
        migrated.append(
            replace(
                item,
                schedule=_legacy_schedule(word, index),
                encounters=encounters,
                extra_data=str(word.get("extra_data", "")),
                sentence_mining=(
                    word.get("sentence_mining")
                    if isinstance(word.get("sentence_mining"), dict)
                    and word.get("sentence_mining")
                    else None
                ),
            )
        )

    for index, word in enumerate(words):
        if index in matched_words:
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
                    VocabularyEncounter(
                        context=context,
                        observed_at=float(word.get("added_at", 0.0) or index + 1),
                    ),
                )
                if context
                else (),
                schedule=_legacy_schedule(word, index),
                extra_data=str(word.get("extra_data", "")),
                sentence_mining=(
                    word.get("sentence_mining")
                    if isinstance(word.get("sentence_mining"), dict)
                    and word.get("sentence_mining")
                    else None
                ),
            )
        )
    return migrated


def _grammar_item_from_dict(data: dict) -> GrammarMemoryItem:
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


def _grammar_item_to_dict(item: GrammarMemoryItem) -> dict:
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


def _is_due(item: LexicalItem, now: float) -> bool:
    """A reviewed word is due once next_review is within the look-ahead window
    (or already overdue — FSRS folds lateness into the next interval)."""
    return (
        item.schedule.review_count >= 0
        and item.schedule.next_review_at - now <= REVIEW_WINDOW_HOURS * 3600
    )


# ---------------------------------------------------------------------------
# String normalization for algorithmic matching (spec 3.4, step 1)
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-zа-яё0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _similar(a: str, b: str) -> bool:
    """Simple string similarity without LLM (spec 3.4 — 'similar words' delegation)."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return False


# ---------------------------------------------------------------------------
# UserStorage
# ---------------------------------------------------------------------------

@dataclass
class UserStorage:
    username: str
    lexical_items: list[LexicalItem] = field(default_factory=list)
    lesson_topics: list[LessonTopic] = field(default_factory=list)
    grammar_memory: list[GrammarMemoryItem] = field(default_factory=list)
    settings: UserSettings = field(default_factory=UserSettings)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, username: str) -> "UserStorage":
        data = db.kb_get(username)
        settings = UserSettings(**(db.settings_get(username) or {}))
        if data is None:
            log.info("[storage] no KB for user %r, starting empty", username)
            return cls(username=username, settings=settings)

        migrated = "lexical_items" not in data
        lexical_items = (
            _migrate_legacy_lexical_items(data, settings.target_lang)
            if migrated
            else [
                _lexical_item_from_dict(item)
                for item in data.get("lexical_items", [])
                if isinstance(item, dict)
            ]
        )

        storage = cls(
            username=username,
            lexical_items=lexical_items,
            lesson_topics=[LessonTopic.from_dict(t) for t in data.get("lesson_topics", [])],
            grammar_memory=[
                _grammar_item_from_dict(item)
                for item in data.get("grammar_memory", [])
                if isinstance(item, dict)
            ],
            settings=settings,
        )
        log.info(
            "[storage] loaded KB for user %r: %d lexical items, %d topics, onboarded=%s",
            username,
            len(storage.lexical_items),
            len(storage.lesson_topics),
            storage.settings.is_onboarded(),
        )
        if migrated:
            log.info("[storage] migrating legacy words for user %r to LexicalItem v2", username)
            storage.save()
        return storage

    def save(self) -> None:
        db.kb_set(self.username, {
            "schema_version": 2,
            "lexical_items": [
                _lexical_item_to_dict(item) for item in self.lexical_items
            ],
            "lesson_topics": [t.to_dict() for t in self.lesson_topics],
            "grammar_memory": [
                _grammar_item_to_dict(item) for item in self.grammar_memory
            ],
        })
        db.settings_set(self.username, self.settings)
        log.debug(
            "[storage] saved KB for user %r: %d lexical items, %d topics",
            self.username, len(self.lexical_items), len(self.lesson_topics),
        )

    # ------------------------------------------------------------------
    # Word / topic search
    # ------------------------------------------------------------------

    def find_lexical_item(self, item_id: str) -> Optional[LexicalItem]:
        return next(
            (item for item in self.lexical_items if item.item_id == item_id), None
        )

    def find_lexical_item_by_term(self, term: str) -> Optional[LexicalItem]:
        normalized = _normalize(term)
        for item in self.lexical_items:
            if (
                item.language == self.settings.target_lang
                and _normalize(item.term) == normalized
                and item.status in {"learning", "known"}
            ):
                return item
        return None

    def delete_lexical_item(self, item_id: str) -> bool:
        item = self.find_lexical_item(item_id)
        if item is None:
            return False
        self.lexical_items.remove(item)
        return True

    def find_lesson_topic(self, name: str) -> Optional[LessonTopic]:
        n = _normalize(name)
        for t in self.lesson_topics:
            if _normalize(t.name) == n:
                return t
        return None

    def candidates_for_delete_word(self, query: str) -> list[LexicalItem]:
        """Spec 3.4: algorithmically filtered 'similar' words — LLM candidate set."""
        return [item for item in self.lexical_items if _similar(item.term, query)]

    def candidates_for_delete_topic(self, query: str) -> list[LessonTopic]:
        return [t for t in self.lesson_topics if _similar(t.name, query)]

    # ------------------------------------------------------------------
    # apply_kb_changes (spec 3.4)
    # ------------------------------------------------------------------

    def apply_kb_changes(self, patches: list[Patch]) -> list[str]:
        """
        Apply a list of patches to the KB. Returns notification messages for
        the user (e.g. "word X not found for deletion").

        Invalid / not-found add_* patches are silently skipped (spec 6, p.1).
        For delete_* with no match — a short note is returned.
        """
        log.info(
            "[apply_kb_changes] applying %d patch(es) for user %r: %s",
            len(patches), self.username, [(p.type, p.value) for p in patches],
        )
        notes: list[str] = []

        for patch in patches:
            try:
                if patch.type == "add_word":
                    added = self._add_word(patch)
                    log.info("[apply_kb_changes] add_word %r -> %s", patch.value, "added" if added else "skipped (duplicate)")
                elif patch.type == "delete_word":
                    if not self._delete_word(patch.value):
                        log.info("[apply_kb_changes] delete_word %r -> not found", patch.value)
                        notes.append(f"Word \"{patch.value}\" not found in your vocabulary.")
                    else:
                        log.info("[apply_kb_changes] delete_word %r -> deleted", patch.value)
                elif patch.type == "add_topic":
                    added = self._add_topic(patch)
                    log.info("[apply_kb_changes] add_topic %r -> %s", patch.value, "added" if added else "skipped (duplicate)")
                elif patch.type == "delete_topic":
                    if not self._delete_topic(patch.value):
                        log.info("[apply_kb_changes] delete_topic %r -> not found", patch.value)
                        notes.append(f"Topic \"{patch.value}\" not found.")
                    else:
                        log.info("[apply_kb_changes] delete_topic %r -> deleted", patch.value)
                elif patch.type == "mark_known":
                    if not self._mark_known(patch.value):
                        log.info("[apply_kb_changes] mark_known %r -> not found", patch.value)
                        notes.append(f"Word \"{patch.value}\" not found to mark as learned.")
                    else:
                        log.info("[apply_kb_changes] mark_known %r -> marked known", patch.value)
                else:
                    log.warning("[apply_kb_changes] unknown patch type: %s", patch.type)
            except Exception:
                log.exception("[apply_kb_changes] failed to apply patch %r", patch)

        if patches:
            self.save()

        log.info("[apply_kb_changes] done, notes=%s", notes)
        return notes

    def _add_word(self, patch: Patch) -> bool:
        existing = self.find_lexical_item_by_term(patch.value)
        if existing is not None:
            # Word already in KB — no duplicates (spec 3.1: "only if not already in KB")
            return False
        next_review = 0.0
        if patch.counter >= 0:
            next_review = time.time() + FIRST_REVIEW_DELAY_DAYS * 24 * 3600
        added_at = time.time()
        self.lexical_items.append(
            LexicalItem(
                item_id=lexical_item_id(
                    patch.value, self.settings.target_lang, ""
                ),
                term=patch.value,
                language=self.settings.target_lang,
                translation="",
                status="known" if bool(patch.known) else "learning",
                encounters=(
                    VocabularyEncounter(context=patch.context, observed_at=added_at),
                )
                if patch.context
                else (),
                schedule=ReviewSchedule(
                    review_count=patch.counter,
                    next_review_at=next_review,
                    added_at=added_at,
                ),
            )
        )
        return True

    def _delete_word(self, query: str) -> bool:
        item = self.find_lexical_item_by_term(query)
        if item is None:
            return False
        self.lexical_items.remove(item)
        return True

    def _add_topic(self, patch: Patch) -> bool:
        if self.find_lesson_topic(patch.value) is not None:
            return False
        self.lesson_topics.append(LessonTopic(name=patch.value))
        return True

    def _delete_topic(self, query: str) -> bool:
        t = self.find_lesson_topic(query)
        if t is None:
            return False
        self.lesson_topics.remove(t)
        return True

    def _mark_known(self, query: str) -> bool:
        """
        Special case "word learned" (spec 3.4): marks known=True and removes
        the word from the collect_train_word pool without deleting it from KB.
        """
        item = self.find_lexical_item_by_term(query)
        if item is None:
            return False
        self.replace_lexical_item(
            replace(
                item,
                status="known",
                schedule=replace(item.schedule, delayed=False),
            )
        )
        return True

    def replace_lexical_item(self, updated: LexicalItem) -> None:
        index = next(
            (
                index
                for index, item in enumerate(self.lexical_items)
                if item.item_id == updated.item_id
            ),
            None,
        )
        if index is None:
            raise ValueError("lexical item not found")
        self.lexical_items[index] = updated

    def due_count(self) -> int:
        """Number of lexical senses ready for review right now."""
        now = time.time()
        return sum(
            1
            for item in self.lexical_items
            if item.status == "learning" and _is_due(item, now)
        )

    def apply_review_result(
        self, item: LexicalItem, outcome: str, task_type: str = ""
    ) -> LexicalItem:
        """
        Update the word's FSRS memory state after a review and append a row to
        the review log:
          - outcome "correct"/"vague"/"incorrect" maps to Good/Hard/Again
            (other outcomes are ignored — not a review);
          - first review initializes stability/difficulty, later ones update
            them from the actual elapsed time;
          - counter keeps counting reviews (and still flips -1 -> reviewed,
            which the UI uses as the "new word" badge);
          - next_review = now + FSRS interval for the desired retention.
        """
        rating = fsrs.outcome_to_rating(outcome)
        if rating is None:
            log.info(
                "[apply_review_result] user %r: item=%r outcome=%r is not a review, skipping",
                self.username, item.item_id, outcome,
            )
            return item

        now = time.time()
        schedule = item.schedule
        if schedule.stability > 0 and schedule.last_review_at > 0:
            elapsed_days = max(0.0, (now - schedule.last_review_at) / 86400)
            retrievability: Optional[float] = fsrs.retrievability(
                elapsed_days, schedule.stability
            )
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
            max(fsrs.interval_days(state.stability, FSRS_DESIRED_RETENTION), FSRS_MIN_INTERVAL_DAYS),
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
        self.replace_lexical_item(updated)

        db.review_log_add(
            username=self.username,
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
            "[apply_review_result] user %r: item=%s term=%r outcome=%s rating=%d -> S=%.2f D=%.2f "
            "R=%s next_review=%s (+%.2fd)",
            self.username,
            item.item_id,
            item.term,
            outcome,
            rating,
            updated.schedule.stability,
            updated.schedule.difficulty,
            f"{retrievability:.2f}" if retrievability is not None else "-",
            datetime.fromtimestamp(updated.schedule.next_review_at).isoformat(),
            interval_days,
        )
        return updated

    def apply_overdue_decay(self) -> list[LexicalItem]:
        """
        Flag senses overdue by more than REVIEW_WINDOW_HOURS. This does not
        change their review count or due timestamp: FSRS folds lateness into
        the next interval through lower retrievability at review time.

        Returns the newly flagged lexical items for logging and reminders.
        """
        now = time.time()
        window_seconds = REVIEW_WINDOW_HOURS * 3600
        affected: list[LexicalItem] = []

        for item in tuple(self.lexical_items):
            schedule = item.schedule
            if (
                item.status == "learning"
                and schedule.review_count >= 0
                and not schedule.delayed
                and now - schedule.next_review_at > window_seconds
            ):
                updated = replace(item, schedule=replace(schedule, delayed=True))
                self.replace_lexical_item(updated)
                affected.append(updated)
                log.info(
                    "[apply_overdue_decay] user %r: item=%s term=%r overdue",
                    self.username,
                    item.item_id,
                    item.term,
                )

        if affected:
            self.save()

        return affected

    # ------------------------------------------------------------------
    # Misc counters (for stats / commands)
    # ------------------------------------------------------------------

    def learning_count(self) -> int:
        return sum(1 for item in self.lexical_items if item.status == "learning")

    def known_count(self) -> int:
        return sum(1 for item in self.lexical_items if item.status == "known")


# ---------------------------------------------------------------------------
# Storage registry — one shared UserStorage object per user for the process
# lifetime, so concurrent handlers (HTTP + WebSockets + background tasks)
# mutate the same object instead of clobbering each other's saves.
# ---------------------------------------------------------------------------

_storages: dict[str, UserStorage] = {}


def get_storage(username: str) -> UserStorage:
    if username not in _storages:
        _storages[username] = UserStorage.load(username)
    return _storages[username]


def drop_storage(username: str) -> None:
    """Forget the cached object (used by debug reset)."""
    _storages.pop(username, None)
