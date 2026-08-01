"""Atomic user-document storage composed from focused repositories."""

from __future__ import annotations

import logging

import db
from models import UserSettings
from repositories import GrammarMemoryRepository, LessonRepository, LexiconRepository


log = logging.getLogger(__name__)


class UserStorage:
    """Coordinates one atomic document; domain collections live in repositories."""

    def __init__(
        self,
        username: str,
        *,
        lexicon: LexiconRepository | None = None,
        lessons: LessonRepository | None = None,
        grammar: GrammarMemoryRepository | None = None,
        settings: UserSettings | None = None,
    ) -> None:
        self.username = username
        self.lexicon = lexicon if lexicon is not None else LexiconRepository(username)
        self.lessons = lessons if lessons is not None else LessonRepository()
        self.grammar = grammar if grammar is not None else GrammarMemoryRepository()
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
        storage = cls(
            username,
            lexicon=lexicon,
            lessons=LessonRepository.from_document(document.get("lesson_topics")),
            grammar=GrammarMemoryRepository.from_document(document.get("grammar_memory")),
            settings=settings,
        )
        log.info(
            "[storage] loaded user %r: %d lexical items, %d lessons, %d grammar items",
            username,
            len(storage.lexicon),
            len(storage.lessons),
            len(storage.grammar),
        )
        if migrated:
            log.info("[storage] migrating user %r to LexicalItem v2", username)
            storage.save()
        return storage

    def save(self) -> None:
        db.kb_set(
            self.username,
            {
                "schema_version": 2,
                "lexical_items": self.lexicon.to_document(),
                "lesson_topics": self.lessons.to_document(),
                "grammar_memory": self.grammar.to_document(),
            },
        )
        db.settings_set(self.username, self.settings)


_storages: dict[str, UserStorage] = {}


def get_storage(username: str) -> UserStorage:
    if username not in _storages:
        _storages[username] = UserStorage.load(username)
    return _storages[username]


def drop_storage(username: str) -> None:
    _storages.pop(username, None)
