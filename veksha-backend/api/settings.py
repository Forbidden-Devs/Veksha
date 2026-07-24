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
import os
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import llm
import db
from auth import CurrentUser
from config import REMINDER_MIN_WORDS, REVIEW_WINDOW_HOURS, SCHEDULER_INTERVAL_MINUTES
from cefr import BANDS, band_index, level_to_cefr
from learning_core_v2.dictionary import DictionaryLookupRequest
from learning_core_v2.lesson import TopicReviewPolicy
from learning_core_v2_adapters.lesson import UserStorageLessonRepository
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import build_dictionary_enrichment
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
    mining_same_level_examples: int | None = Field(None, ge=1, le=5)
    mining_higher_level_examples: int | None = Field(None, ge=0, le=3)


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
    mining_same_level_examples: int = 2
    mining_higher_level_examples: int = 1
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


class MiningExampleResponse(BaseModel):
    sentence: str
    translation: str = ""
    level: str
    is_higher: bool = False


class MiningCollocationResponse(BaseModel):
    text: str
    translation: str = ""


class SentenceMiningResponse(BaseModel):
    examples: list[MiningExampleResponse] = Field(default_factory=list)
    mnemonic: str = ""
    collocations: list[MiningCollocationResponse] = Field(default_factory=list)
    config: dict[str, str | int] = Field(default_factory=dict)


class WordEntryResponse(BaseModel):
    name: str
    context: str
    translation: str = ""
    transcription: str = ""
    counter: int
    known: bool
    next_review: float
    added_at: float
    sentence_mining: SentenceMiningResponse | None = None


class KBWordsResponse(BaseModel):
    words: list[WordEntryResponse]


class WordReviewRequest(BaseModel):
    word: str
    rating: str


class AddWordRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=200)


class SentenceMiningRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=200)
    force: bool = False


def _topic_needing_review(storage: UserStorage) -> str | None:
    topics = UserStorageLessonRepository(storage).topics()
    return TopicReviewPolicy().first_due(topics)


def _dictionary_v2_enabled() -> bool:
    return os.getenv("VEKSHA_CORE_V2_DICTIONARY_ENABLED", "0").lower() in {
        "1",
        "true",
        "yes",
    }


async def _dictionary_details(storage: UserStorage, entry) -> dict[str, str]:
    if not _dictionary_v2_enabled():
        return await llm.translate_selection(
            entry.name,
            storage.settings.target_lang,
            storage.settings.native_lang,
            level=storage.settings.english_level or "intermediate",
        )

    try:
        result = await build_dictionary_enrichment().execute(
            DictionaryLookupRequest(
                term=entry.name,
                learning_language=storage.settings.target_lang,
                native_language=storage.settings.native_lang,
                proficiency=storage.settings.english_level or "intermediate",
                context=entry.context or "",
            )
        )
    except (LanguageProviderError, ValueError) as exc:
        log.warning("core-v2 dictionary enrichment unavailable: %s", exc)
        return {}
    return {
        "headword": result.headword,
        "translation": result.translation,
        "transcription": result.transcription,
    }


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
        mining_same_level_examples=s.mining_same_level_examples,
        mining_higher_level_examples=s.mining_higher_level_examples,
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
    for lang in target_langs:
        language_settings.setdefault(lang, {"level": "", "goals": "", "prompt": ""})
    # Persist languages in the same normalized order returned to clients.
    # Keeping the active language first prevents stale insertion order from
    # making another language appear active in list-based UI.
    language_settings = {lang: language_settings[lang] for lang in target_langs}
    storage.settings = UserSettings(
        display_name=display_name,
        native_lang=req.native_lang,
        target_lang=req.target_lang,
        language_settings=language_settings,
        reminder_level=req.reminder_level,
        overseer=req.overseer,
        mining_same_level_examples=(
            req.mining_same_level_examples
            if req.mining_same_level_examples is not None
            else storage.settings.mining_same_level_examples
        ),
        mining_higher_level_examples=(
            req.mining_higher_level_examples
            if req.mining_higher_level_examples is not None
            else storage.settings.mining_higher_level_examples
        ),
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
        key=lambda w: w.name.casefold(),
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
            added_at=w.added_at,
        )
        for w in words
    ])


@router.post("/api/kb_word", response_model=WordEntryResponse)
async def api_add_kb_word(req: AddWordRequest, username: CurrentUser) -> WordEntryResponse:
    """Add a tracked word and synchronously populate its dictionary fields."""
    storage = get_storage(username)
    word = " ".join(req.word.split()).lower()
    entry = storage.find_word(word)
    created = entry is None
    if created:
        storage.apply_kb_changes([
            Patch(type="add_word", value=word, context="", counter=0, known=False)
        ])
        entry = storage.find_word(word)
    if entry is None:  # defensive: storage rejected an invalid patch
        raise HTTPException(status_code=400, detail="Could not add word.")

    if not entry.translation or not entry.transcription:
        result = await _dictionary_details(storage, entry)
        if not result.get("translation"):
            if created:
                storage.apply_kb_changes([Patch(type="delete_word", value=entry.name)])
            raise HTTPException(status_code=502, detail="Could not generate dictionary details.")
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
        added_at=entry.added_at,
        sentence_mining=SentenceMiningResponse(**entry.sentence_mining) if entry.sentence_mining else None,
    )


@router.get("/api/kb_word_details", response_model=WordEntryResponse)
async def api_kb_word_details(word: str, username: CurrentUser) -> WordEntryResponse:
    storage = get_storage(username)
    entry = storage.find_word(word)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found.")
    if not entry.translation or not entry.transcription:
        result = await _dictionary_details(storage, entry)
        if not result.get("translation"):
            raise HTTPException(status_code=502, detail="Could not generate dictionary details.")
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
        added_at=entry.added_at,
        sentence_mining=SentenceMiningResponse(**entry.sentence_mining) if entry.sentence_mining else None,
    )


@router.post("/api/kb_word_mine", response_model=WordEntryResponse)
async def api_mine_kb_word(req: SentenceMiningRequest, username: CurrentUser) -> WordEntryResponse:
    storage = get_storage(username)
    entry = storage.find_word(req.word)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found.")

    level = level_to_cefr(storage.settings.english_level)
    higher_level = BANDS[min(band_index(level) + 1, len(BANDS) - 1)]
    same_count = storage.settings.mining_same_level_examples
    higher_count = storage.settings.mining_higher_level_examples
    config: dict[str, str | int] = {
        "level": level,
        "higher_level": higher_level,
        "same_count": same_count,
        "higher_count": higher_count,
    }

    if req.force or not entry.sentence_mining or entry.sentence_mining.get("config") != config:
        card = await llm.generate_sentence_mining(
            word=entry.name,
            translation=entry.translation,
            context=entry.context,
            target_lang=storage.settings.target_lang,
            native_lang=storage.settings.native_lang,
            level=level,
            higher_level=higher_level,
            same_count=same_count,
            higher_count=higher_count,
        )
        if not card.get("examples"):
            raise HTTPException(status_code=503, detail="Could not generate Sentence Mining card.")
        entry.sentence_mining = {**card, "config": config}
        storage.save()

    return WordEntryResponse(
        name=entry.name,
        context=entry.context,
        translation=entry.translation,
        transcription=entry.transcription,
        counter=entry.counter,
        known=bool(entry.known),
        next_review=entry.next_review,
        added_at=entry.added_at,
        sentence_mining=SentenceMiningResponse(**entry.sentence_mining),
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
