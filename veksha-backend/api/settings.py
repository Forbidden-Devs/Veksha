"""
api/settings.py — settings, reminders, and KB summary endpoints.

  GET  /api/settings    — current user settings
  POST /api/settings    — save settings
  GET  /api/reminders   — for chrome.alarms: check due words / topics
  GET  /api/kb_summary  — vocabulary counters for the UI header
  GET  /api/kb_words    — full word list
  DELETE /api/kb_word   — remove one word
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from config import REMINDER_MIN_WORDS, REVIEW_WINDOW_HOURS, SCHEDULER_INTERVAL_MINUTES
from models import VALID_ENGLISH_LEVELS, Patch, UserSettings
from storage import UserStorage, get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class SettingsRequest(BaseModel):
    english_level: str | None = None
    goals: str = ""
    general_prompt: str = ""
    native_lang: str = ""
    target_lang: str = "en"
    reminder_level: int = Field(2, ge=1, le=3)
    overseer: bool = False


class SettingsResponse(BaseModel):
    english_level: str | None = None
    goals: str = ""
    general_prompt: str = ""
    native_lang: str = ""
    target_lang: str = "en"
    reminder_level: int = 2
    overseer: bool = False
    is_onboarded: bool = False


class RemindersResponse(BaseModel):
    due_words: int
    due_word_names: list[str] = Field(default_factory=list)
    due_topic: str | None = None
    should_remind: bool
    poll_interval_minutes: int = SCHEDULER_INTERVAL_MINUTES


class KBSummaryResponse(BaseModel):
    learning_count: int
    known_count: int
    topics_count: int


class WordEntryResponse(BaseModel):
    name: str
    context: str
    counter: int
    known: bool
    next_review: float


class KBWordsResponse(BaseModel):
    words: list[WordEntryResponse]


def _topic_needing_review(storage: UserStorage) -> str | None:
    """First lesson topic with generated blocks that are not yet mastered."""
    from lesson import MASTERY_THRESHOLD, _block_has_content

    for topic in storage.lesson_topics:
        ready = [b for b in topic.blocks if _block_has_content(b)]
        if ready and any(b.mastery_score < MASTERY_THRESHOLD for b in ready):
            return topic.name
    return None


def _due_word_names(storage: UserStorage, limit: int = 8) -> list[str]:
    now = time.time()
    window_seconds = REVIEW_WINDOW_HOURS * 3600
    words = [
        w for w in storage.words
        if (w.known is False or w.known == "")
        and w.counter >= 0
        and w.next_review - now <= window_seconds  # due or overdue (FSRS)
    ]
    words.sort(key=lambda w: (w.next_review, -w.counter, w.name.lower()))
    return [w.name for w in words[:limit]]


def _settings_response(storage: UserStorage) -> SettingsResponse:
    s = storage.settings
    return SettingsResponse(
        english_level=s.english_level,
        goals=s.goals,
        general_prompt=s.general_prompt,
        native_lang=s.native_lang,
        target_lang=s.target_lang,
        reminder_level=s.reminder_level,
        overseer=s.overseer,
        is_onboarded=s.is_onboarded(),
    )


@router.get("/api/settings", response_model=SettingsResponse)
async def api_get_settings(username: CurrentUser) -> SettingsResponse:
    return _settings_response(get_storage(username))


@router.post("/api/settings", response_model=SettingsResponse)
async def api_post_settings(req: SettingsRequest, username: CurrentUser) -> SettingsResponse:
    if req.english_level is not None and req.english_level not in VALID_ENGLISH_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid english_level. Must be one of: {', '.join(VALID_ENGLISH_LEVELS)}",
        )
    storage = get_storage(username)
    # Preserve the stored level when the client omits it (partial update).
    level = req.english_level if req.english_level is not None else storage.settings.english_level
    storage.settings = UserSettings(
        english_level=level,
        goals=req.goals,
        general_prompt=req.general_prompt,
        native_lang=req.native_lang,
        target_lang=req.target_lang,
        reminder_level=req.reminder_level,
        overseer=req.overseer,
    )
    storage.save()
    log.info(
        "[settings] user %r updated: level=%s goals=%r native=%r target=%r",
        username, level, req.goals, req.native_lang, req.target_lang,
    )
    return _settings_response(storage)


@router.get("/api/reminders", response_model=RemindersResponse)
async def api_reminders(username: CurrentUser) -> RemindersResponse:
    storage = get_storage(username)
    decayed = storage.apply_overdue_decay()
    if decayed:
        log.info("[reminders] user %r: %d word(s) decayed", username, len(decayed))
    due_words = storage.due_count()
    due_word_names = _due_word_names(storage)
    due_topic = _topic_needing_review(storage)
    return RemindersResponse(
        due_words=due_words,
        due_word_names=due_word_names,
        due_topic=due_topic,
        should_remind=due_words >= REMINDER_MIN_WORDS or due_topic is not None,
    )


@router.get("/api/kb_summary", response_model=KBSummaryResponse)
async def api_kb_summary(username: CurrentUser) -> KBSummaryResponse:
    storage = get_storage(username)
    return KBSummaryResponse(
        learning_count=storage.learning_count(),
        known_count=storage.known_count(),
        topics_count=len(storage.lesson_topics),
    )


@router.delete("/api/kb_word")
async def api_delete_kb_word(word: str, username: CurrentUser) -> dict:
    storage = get_storage(username)
    storage.apply_kb_changes([Patch(type="delete_word", value=word)])
    log.info("[kb_word] deleted word=%r for user=%r", word, username)
    return {"ok": True}


@router.get("/api/kb_words", response_model=KBWordsResponse)
async def api_kb_words(username: CurrentUser) -> KBWordsResponse:
    storage = get_storage(username)
    words = sorted(storage.words, key=lambda w: (w.known is True, w.name.lower()))
    return KBWordsResponse(words=[
        WordEntryResponse(
            name=w.name,
            context=w.context or "",
            counter=w.counter,
            known=bool(w.known),
            next_review=w.next_review,
        )
        for w in words
    ])
