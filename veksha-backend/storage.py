"""Atomic user-document storage composed from focused repositories."""

from __future__ import annotations

import logging

import db
from learning_core_v2.goal import LearnerProfile
from models import UserSettings
from repositories import (
    GoalRepository,
    GrammarMemoryRepository,
    LexiconRepository,
    SubtitleSessionRepository,
)


log = logging.getLogger(__name__)


def learner_profile(settings: UserSettings) -> LearnerProfile:
    """The constraints a new goal inherits from the learner's settings."""
    return LearnerProfile(
        proficiency=settings.english_level or "intermediate",
        native_language=settings.native_lang or "en",
        learning_language=settings.target_lang or "en",
    )


class UserStorage:
    """Coordinates one atomic document; domain collections live in repositories."""

    def __init__(
        self,
        username: str,
        *,
        lexicon: LexiconRepository | None = None,
        goals: GoalRepository | None = None,
        grammar: GrammarMemoryRepository | None = None,
        subtitle_sessions: SubtitleSessionRepository | None = None,
        settings: UserSettings | None = None,
    ) -> None:
        self.username = username
        self.lexicon = lexicon if lexicon is not None else LexiconRepository(username)
        self.goals = goals if goals is not None else GoalRepository()
        self.grammar = grammar if grammar is not None else GrammarMemoryRepository()
        self.subtitle_sessions = (
            subtitle_sessions
            if subtitle_sessions is not None
            else SubtitleSessionRepository()
        )
        self.settings = settings if settings is not None else UserSettings()

    @classmethod
    def load(cls, username: str) -> "UserStorage":
        document = db.kb_get(username)
        settings = UserSettings(**(db.settings_get(username) or {}))
        if document is None:
            log.info("[storage] no KB for user %r, starting empty", username)
            return cls(username, settings=settings)

        lexicon, migrated = LexiconRepository.from_document(
            username,
            document,
            settings.target_lang,
        )
        profile = learner_profile(settings)
        goals, goals_migrated = _load_goals(document, profile)
        storage = cls(
            username,
            lexicon=lexicon,
            goals=goals,
            grammar=GrammarMemoryRepository.from_document(document.get("grammar_memory")),
            subtitle_sessions=SubtitleSessionRepository.from_document(
                document.get("subtitle_sessions")
            ),
            settings=settings,
        )
        log.info(
            "[storage] loaded user %r: %d lexical items, %d goals, %d grammar items",
            username,
            len(storage.lexicon),
            len(storage.goals),
            len(storage.grammar),
        )
        if migrated or goals_migrated:
            log.info("[storage] rewriting user %r into the current schema", username)
            storage.save()
        return storage

    def save(self) -> None:
        db.kb_set(
            self.username,
            {
                "schema_version": 4,
                "lexical_items": self.lexicon.to_document(),
                "learning_goals": self.goals.to_document(),
                "grammar_memory": self.grammar.to_document(),
                "subtitle_sessions": self.subtitle_sessions.to_document(),
            },
        )
        db.settings_set(self.username, self.settings)


def _load_goals(
    document: dict, profile: LearnerProfile
) -> tuple[GoalRepository, bool]:
    """Read goals, falling back once to the pre-goal lesson topics."""
    if isinstance(document.get("learning_goals"), list):
        return GoalRepository.from_document(document["learning_goals"], profile), False
    legacy = GoalRepository.from_legacy_topics(document.get("lesson_topics"), profile)
    return legacy, len(legacy) > 0


class _StorageRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, UserStorage] = {}

    def obtain(self, username: str) -> UserStorage:
        storage = self._entries.get(username)
        if storage is None:
            storage = UserStorage.load(username)
            self._entries[username] = storage
        return storage

    def discard(self, username: str) -> None:
        self._entries.pop(username, None)


_registry = _StorageRegistry()


def get_storage(username: str) -> UserStorage:
    return _registry.obtain(username)


def drop_storage(username: str) -> None:
    _registry.discard(username)
