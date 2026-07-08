"""
storage.py — user Knowledge Base storage.

The KB (words, lesson topics, settings) is persisted as one JSON document per
user in SQLite (see db.py); this module keeps the in-memory object model and
the spaced-repetition primitives on top of it.

Implements:
  - apply_kb_changes — apply {type, value} patches to KB
  - collect_train_word — deterministic word selection for training
  - helper methods for LLM candidate matching (delete_word / delete_topic)
"""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field
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
from models import LessonTopic, Patch, UserSettings, Word

log = logging.getLogger(__name__)


def _is_due(word: Word, now: float) -> bool:
    """A reviewed word is due once next_review is within the look-ahead window
    (or already overdue — FSRS folds lateness into the next interval)."""
    return word.counter >= 0 and word.next_review - now <= REVIEW_WINDOW_HOURS * 3600


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
    words: list[Word] = field(default_factory=list)
    lesson_topics: list[LessonTopic] = field(default_factory=list)
    settings: UserSettings = field(default_factory=UserSettings)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, username: str) -> "UserStorage":
        data = db.kb_get(username)
        if data is None:
            log.info("[storage] no KB for user %r, starting empty", username)
            return cls(username=username)

        storage = cls(
            username=username,
            words=[Word.from_dict(w) for w in data.get("words", [])],
            lesson_topics=[LessonTopic.from_dict(t) for t in data.get("lesson_topics", [])],
            settings=UserSettings.from_dict(data.get("settings", {})),
        )
        log.info(
            "[storage] loaded KB for user %r: %d words, %d topics, onboarded=%s",
            username, len(storage.words), len(storage.lesson_topics), storage.settings.is_onboarded(),
        )
        return storage

    def save(self) -> None:
        db.kb_set(self.username, {
            "words": [w.to_dict() for w in self.words],
            "lesson_topics": [t.to_dict() for t in self.lesson_topics],
            "settings": self.settings.to_dict(),
        })
        log.debug(
            "[storage] saved KB for user %r: %d words, %d topics",
            self.username, len(self.words), len(self.lesson_topics),
        )

    # ------------------------------------------------------------------
    # Word / topic search
    # ------------------------------------------------------------------

    def find_word(self, name: str) -> Optional[Word]:
        n = _normalize(name)
        for w in self.words:
            if _normalize(w.name) == n:
                return w
        return None

    def find_lesson_topic(self, name: str) -> Optional[LessonTopic]:
        n = _normalize(name)
        for t in self.lesson_topics:
            if _normalize(t.name) == n:
                return t
        return None

    def candidates_for_delete_word(self, query: str) -> list[Word]:
        """Spec 3.4: algorithmically filtered 'similar' words — LLM candidate set."""
        return [w for w in self.words if _similar(w.name, query)]

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
        existing = self.find_word(patch.value)
        if existing is not None:
            # Word already in KB — no duplicates (spec 3.1: "only if not already in KB")
            return False
        next_review = 0.0
        if patch.counter >= 0:
            next_review = time.time() + FIRST_REVIEW_DELAY_DAYS * 24 * 3600
        self.words.append(
            Word(
                name=patch.value,
                context=patch.context,
                counter=patch.counter,
                known=patch.known,
                delayed=False,
                next_review=next_review,
                extra_data="",
            )
        )
        return True

    def _delete_word(self, query: str) -> bool:
        w = self.find_word(query)
        if w is None:
            return False
        self.words.remove(w)
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
        w = self.find_word(query)
        if w is None:
            return False
        w.known = True
        w.delayed = False
        # collect_train_word only picks words with known == False
        return True

    # ------------------------------------------------------------------
    # collect_train_word (spec 4.1.1, FSRS scheduling — see fsrs.py)
    # ------------------------------------------------------------------

    def collect_train_word(self) -> Optional[Word]:
        """
        Deterministic word selection for training:
          1. Pool = words with known == False that are due (next_review within
             the look-ahead window or overdue).
             If no such pool — pool = words with known == False and counter == -1
             ("new" words, not yet introduced to rotation).
          2. Base weight 1, delayed=True → weight 2.
          3. Weighted random selection.

        Returns None if KB has no suitable words
        (spec 6, p.4 — empty-KB handling is delegated to caller).
        """
        now = time.time()

        active = [w for w in self.words if w.known is False or w.known == ""]

        pool = [w for w in active if _is_due(w, now)]
        pool_kind = "due (within review window)"
        if not pool:
            pool = [w for w in active if w.counter == -1]
            pool_kind = "counter==-1 (new words, fallback)"

        if not pool:
            log.info("[collect_train_word] user %r: pool empty (active=%d) -> None", self.username, len(active))
            return None

        weights = [2 if w.delayed else 1 for w in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        log.info(
            "[collect_train_word] user %r: pool=%s (size=%d) -> chosen=%r (counter=%d delayed=%s next_review=%s)",
            self.username, pool_kind, len(pool), chosen.name, chosen.counter, chosen.delayed,
            datetime.fromtimestamp(chosen.next_review).isoformat() if chosen.next_review else "(none)",
        )
        return chosen

    def due_count(self) -> int:
        """Number of words ready for review right now (used by reminder scheduler)."""
        now = time.time()
        return sum(
            1 for w in self.words
            if (w.known is False or w.known == "") and _is_due(w, now)
        )

    def apply_review_result(self, word: Word, outcome: str, task_type: str = "") -> None:
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
                "[apply_review_result] user %r: word=%r outcome=%r is not a review, skipping",
                self.username, word.name, outcome,
            )
            return

        now = time.time()
        if word.stability > 0 and word.last_review > 0:
            elapsed_days = max(0.0, (now - word.last_review) / 86400)
            retrievability: Optional[float] = fsrs.retrievability(elapsed_days, word.stability)
            state = fsrs.review(
                fsrs.MemoryState(word.stability, word.difficulty), rating, elapsed_days,
            )
        else:
            elapsed_days = 0.0
            retrievability = None
            state = fsrs.init_state(rating)

        interval_days = min(
            max(fsrs.interval_days(state.stability, FSRS_DESIRED_RETENTION), FSRS_MIN_INTERVAL_DAYS),
            FSRS_MAX_INTERVAL_DAYS,
        )

        word.stability = state.stability
        word.difficulty = state.difficulty
        word.counter = max(word.counter + 1, 1)  # turn -1 into 1
        if rating == fsrs.AGAIN:
            word.lapses += 1
        word.delayed = False
        word.last_review = now
        word.next_review = now + interval_days * 86400

        db.review_log_add(
            username=self.username,
            word=word.name,
            ts=now,
            rating=rating,
            outcome=outcome,
            task_type=task_type,
            elapsed_days=elapsed_days,
            scheduled_days=interval_days,
            stability=word.stability,
            difficulty=word.difficulty,
            retrievability=retrievability,
        )
        log.info(
            "[apply_review_result] user %r: word=%r outcome=%s rating=%d -> S=%.2f D=%.2f "
            "R=%s next_review=%s (+%.2fd)",
            self.username, word.name, outcome, rating, word.stability, word.difficulty,
            f"{retrievability:.2f}" if retrievability is not None else "-",
            datetime.fromtimestamp(word.next_review).isoformat(), interval_days,
        )

    def apply_overdue_decay(self) -> list[Word]:
        """
        Flag words overdue by more than REVIEW_WINDOW_HOURS as delayed=True so
        they get double weight in collect_train_word. Unlike the pre-FSRS
        version this does not touch counter or next_review: lateness is folded
        into the next interval by FSRS itself (low retrievability at review).

        Returns the list of newly flagged words (for logging / notifications).
        """
        now = time.time()
        window_seconds = REVIEW_WINDOW_HOURS * 3600
        affected: list[Word] = []

        for w in self.words:
            if (w.known is False or w.known == "") and w.counter >= 0 and not w.delayed:
                if now - w.next_review > window_seconds:
                    w.delayed = True
                    affected.append(w)
                    log.info(
                        "[apply_overdue_decay] user %r: word=%r overdue -> delayed=True",
                        self.username, w.name,
                    )

        if affected:
            self.save()

        return affected

    def has_any_word(self) -> bool:
        return len(self.words) > 0

    # ------------------------------------------------------------------
    # Misc counters (for stats / commands)
    # ------------------------------------------------------------------

    def learning_count(self) -> int:
        return sum(1 for w in self.words if w.known is False or w.known == "")

    def known_count(self) -> int:
        return sum(1 for w in self.words if w.known is True or (isinstance(w.known, str) and w.known))


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

