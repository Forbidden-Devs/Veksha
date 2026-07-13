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

import llm
import db
from auth import CurrentUser
from config import REMINDER_MIN_WORDS, REVIEW_WINDOW_HOURS, SCHEDULER_INTERVAL_MINUTES
from models import VALID_ENGLISH_LEVELS, Patch, UserSettings
from storage import UserStorage, get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class SettingsRequest(BaseModel):
    display_name: str | None = Field(None, max_length=64)  # None = keep stored value
    english_level: str | None = None
    goals: str = ""
    general_prompt: str = ""
    native_lang: str = ""
    target_lang: str = "en"
    target_langs: list[str] | None = None
    language_settings: dict[str, dict[str, str]] | None = None
    reminder_level: int = Field(2, ge=1, le=3)
    overseer: bool = False


class SettingsResponse(BaseModel):
    display_name: str = ""
    english_level: str | None = None
    goals: str = ""
    general_prompt: str = ""
    native_lang: str = ""
    target_lang: str = "en"
    target_langs: list[str] = Field(default_factory=list)
    language_settings: dict[str, dict[str, str]] = Field(default_factory=dict)
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
    anki_reviews: int
    training_reviews: int


class WordEntryResponse(BaseModel):
    name: str
    context: str
    translation: str = ""
    transcription: str = ""
    counter: int
    known: bool
    next_review: float


class KBWordsResponse(BaseModel):
    words: list[WordEntryResponse]


class WordReviewRequest(BaseModel):
    word: str
    rating: str


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
    language_settings = dict(s.language_settings)
    language_settings.setdefault(s.target_lang, {
        "level": s.english_level or "",
        "goals": s.goals,
        "prompt": s.general_prompt,
    })
    return SettingsResponse(
        # Accounts created before the id/display-name split have no
        # display_name — fall back to their self-chosen account id.
        display_name=s.display_name or storage.username,
        english_level=s.english_level,
        goals=s.goals,
        general_prompt=s.general_prompt,
        native_lang=s.native_lang,
        target_lang=s.target_lang,
        target_langs=s.target_langs or [s.target_lang],
        language_settings=language_settings,
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
    # Preserve stored values when the client omits them (partial update).
    level = req.english_level if req.english_level is not None else storage.settings.english_level
    display_name = (
        req.display_name.strip()
        if req.display_name is not None and req.display_name.strip()
        else storage.settings.display_name
    )
    if req.native_lang == req.target_lang:
        raise HTTPException(status_code=400, detail="Native language cannot be a target language.")
    requested_targets = req.target_langs if req.target_langs is not None else storage.settings.target_langs
    target_langs = [
        lang for lang in dict.fromkeys([req.target_lang, *(requested_targets or [])])
        if lang != req.native_lang
    ]
    language_settings = dict(storage.settings.language_settings)
    if req.language_settings is not None:
        for lang, prefs in req.language_settings.items():
            profile_level = prefs.get("level", "")
            if profile_level and profile_level not in VALID_ENGLISH_LEVELS:
                raise HTTPException(status_code=400, detail=f"Invalid level for {lang}.")
        language_settings.update(req.language_settings)
    language_settings = {
        lang: prefs for lang, prefs in language_settings.items()
        if lang in target_langs
    }
    language_settings.setdefault(req.target_lang, {
        "level": level or "",
        "goals": req.goals,
        "prompt": req.general_prompt,
    })
    storage.settings = UserSettings(
        display_name=display_name,
        native_lang=req.native_lang,
        target_lang=req.target_lang,
        language_settings=language_settings,
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
    review_counts = db.review_log_counts(username)
    return KBSummaryResponse(
        learning_count=storage.learning_count(),
        known_count=storage.known_count(),
        topics_count=len(storage.lesson_topics),
        **review_counts,
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
    words = sorted(
        (w for w in storage.words if w.language == storage.settings.target_lang),
        key=lambda w: (w.known is True, w.name.lower()),
    )
    return KBWordsResponse(words=[
        WordEntryResponse(
            name=w.name,
            context=w.context or "",
            translation=w.translation,
            transcription=w.transcription,
            counter=w.counter,
            known=bool(w.known),
            next_review=w.next_review,
        )
        for w in words
    ])


@router.get("/api/kb_word_details", response_model=WordEntryResponse)
async def api_kb_word_details(word: str, username: CurrentUser) -> WordEntryResponse:
    storage = get_storage(username)
    entry = storage.find_word(word)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found.")
    if not entry.translation or not entry.transcription:
        result = await llm.translate_selection(
            entry.name,
            storage.settings.target_lang,
            storage.settings.native_lang,
            level=storage.settings.english_level or "intermediate",
        )
        entry.translation = result.get("translation", "")
        entry.transcription = result.get("transcription", "")
        storage.save()
    return WordEntryResponse(
        name=entry.name,
        context=entry.context,
        translation=entry.translation,
        transcription=entry.transcription,
        counter=entry.counter,
        known=bool(entry.known),
        next_review=entry.next_review,
    )


@router.post("/api/kb_word_review")
async def api_kb_word_review(req: WordReviewRequest, username: CurrentUser) -> dict:
    storage = get_storage(username)
    entry = storage.find_word(req.word)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found.")
    outcome = "incorrect" if req.rating == "again" else "correct"
    storage.apply_review_result(entry, outcome, task_type="anki")
    storage.save()
    return {"ok": True, "next_review": entry.next_review}
