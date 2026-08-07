"""Repository for resumable subtitle study sessions."""

from __future__ import annotations

from collections.abc import Iterable

from learning_core_v2.subtitle_study import (
    LineStat,
    SubtitleDisplay,
    SubtitleStudySession,
)


# A learner who studies dozens of videos does not need last month's cursors;
# only the open sessions and the most recent finished ones are worth carrying.
MAX_STORED_SESSIONS = 40


class SubtitleSessionRepository:
    def __init__(self, sessions: Iterable[SubtitleStudySession] = ()) -> None:
        self._sessions = list(sessions)

    @classmethod
    def from_document(cls, values: object) -> "SubtitleSessionRepository":
        if not isinstance(values, list):
            return cls()
        return cls(
            _session_from_dict(value) for value in values if isinstance(value, dict)
        )

    def to_document(self) -> list[dict]:
        return [_session_to_dict(session) for session in self._sessions]

    def all(self) -> tuple[SubtitleStudySession, ...]:
        return tuple(self._sessions)

    def find(self, session_id: str) -> SubtitleStudySession | None:
        return next(
            (session for session in self._sessions if session.session_id == session_id),
            None,
        )

    def open_for_media(self, media_key: str) -> SubtitleStudySession | None:
        """The session a learner would expect to walk back into for this video."""
        candidates = [
            session
            for session in self._sessions
            if session.media_key == media_key and session.open
        ]
        return max(candidates, key=lambda session: session.updated_at, default=None)

    def save(self, session: SubtitleStudySession) -> None:
        retained = [
            stored
            for stored in self._sessions
            if stored.session_id != session.session_id
        ]
        self._sessions = [*retained, session][-MAX_STORED_SESSIONS:]

    def remove(self, session_id: str) -> bool:
        session = self.find(session_id)
        if session is None:
            return False
        self._sessions.remove(session)
        return True

    def __len__(self) -> int:
        return len(self._sessions)


def _session_from_dict(data: dict) -> SubtitleStudySession:
    display = data.get("display") if isinstance(data.get("display"), dict) else {}
    return SubtitleStudySession(
        session_id=str(data.get("session_id", "")),
        media_key=str(data.get("media_key", "")),
        media_url=str(data.get("media_url", "")),
        media_title=str(data.get("media_title", "")),
        learning_language=str(data.get("learning_language", "")),
        native_language=str(data.get("native_language", "")),
        display=SubtitleDisplay(
            show_original=bool(display.get("show_original", True)),
            show_translation=bool(display.get("show_translation", True)),
            reveal_on_tap=bool(display.get("reveal_on_tap", False)),
            auto_pause=bool(display.get("auto_pause", False)),
        ),
        check_interval=max(1, int(data.get("check_interval", 5) or 5)),
        cursor_line_id=str(data.get("cursor_line_id", "")),
        cursor_ms=max(0, int(data.get("cursor_ms", 0) or 0)),
        lines_watched=max(0, int(data.get("lines_watched", 0) or 0)),
        lines_since_check=max(0, int(data.get("lines_since_check", 0) or 0)),
        clean_streak=max(0, int(data.get("clean_streak", 0) or 0)),
        checks_asked=max(0, int(data.get("checks_asked", 0) or 0)),
        checks_passed=max(0, int(data.get("checks_passed", 0) or 0)),
        saved_item_ids=tuple(
            str(value) for value in data.get("saved_item_ids", []) if str(value)
        ),
        stats=tuple(
            LineStat(
                line_id=str(value.get("line_id", "")),
                start_ms=max(0, int(value.get("start_ms", 0) or 0)),
                replays=max(0, int(value.get("replays", 0) or 0)),
                slowed=max(0, int(value.get("slowed", 0) or 0)),
                errors=max(0, int(value.get("errors", 0) or 0)),
                saves=max(0, int(value.get("saves", 0) or 0)),
            )
            for value in data.get("stats", [])
            if isinstance(value, dict) and value.get("line_id")
        ),
        started_at=float(data.get("started_at", 0.0) or 0.0),
        updated_at=float(data.get("updated_at", 0.0) or 0.0),
        closed_at=float(data.get("closed_at", 0.0) or 0.0),
    )


def _session_to_dict(session: SubtitleStudySession) -> dict:
    return {
        "session_id": session.session_id,
        "media_key": session.media_key,
        "media_url": session.media_url,
        "media_title": session.media_title,
        "learning_language": session.learning_language,
        "native_language": session.native_language,
        "display": {
            "show_original": session.display.show_original,
            "show_translation": session.display.show_translation,
            "reveal_on_tap": session.display.reveal_on_tap,
            "auto_pause": session.display.auto_pause,
        },
        "check_interval": session.check_interval,
        "cursor_line_id": session.cursor_line_id,
        "cursor_ms": session.cursor_ms,
        "lines_watched": session.lines_watched,
        "lines_since_check": session.lines_since_check,
        "clean_streak": session.clean_streak,
        "checks_asked": session.checks_asked,
        "checks_passed": session.checks_passed,
        "saved_item_ids": list(session.saved_item_ids),
        "stats": [
            {
                "line_id": stat.line_id,
                "start_ms": stat.start_ms,
                "replays": stat.replays,
                "slowed": stat.slowed,
                "errors": stat.errors,
                "saves": stat.saves,
            }
            for stat in session.stats
        ],
        "started_at": session.started_at,
        "updated_at": session.updated_at,
        "closed_at": session.closed_at,
    }
