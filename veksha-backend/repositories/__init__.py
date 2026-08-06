"""Persistence repositories owned by a user's aggregate document."""

from .goals import GoalRepository
from .grammar_memory import GrammarMemoryRepository
from .lexicon import LexiconRepository

__all__ = ["GoalRepository", "GrammarMemoryRepository", "LexiconRepository"]
