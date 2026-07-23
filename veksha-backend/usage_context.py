"""Request-local identity used to attribute successful AI calls."""
from __future__ import annotations

from contextvars import ContextVar


_usage_user: ContextVar[str | None] = ContextVar("ai_usage_user", default=None)


def set_usage_user(username: str) -> None:
    _usage_user.set(username)


def get_usage_user() -> str | None:
    return _usage_user.get()
