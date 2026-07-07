"""
session_state.py — per-user chat history for the assistant pipeline.

Stores the recent assistant-chat exchange (outside of trainings/lessons) in
SQLite (see db.py); the last few messages are passed to the Input Processor
as conversation context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import db

log = logging.getLogger(__name__)

_HISTORY_LIMIT = 30


@dataclass
class SessionState:
    username: str
    history: list[dict] = field(default_factory=list)  # [{"role": "user"|"assistant", "content": "..."}]

    @classmethod
    def load(cls, username: str) -> "SessionState":
        return cls(username=username, history=db.history_get(username))

    def save(self) -> None:
        db.history_set(self.username, self.history)

    def add_history(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        if len(self.history) > _HISTORY_LIMIT:
            self.history = self.history[-_HISTORY_LIMIT:]

    def history_as_text(self, last_n: int = 3) -> str:
        recent = self.history[-last_n:]
        lines = []
        for m in recent:
            prefix = "Bot" if m["role"] == "assistant" else "User"
            lines.append(f"{prefix}: {m['content']}")
        return "\n".join(lines)
