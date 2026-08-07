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
from dataclasses import replace

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentUser
from config import (
    FIRST_REVIEW_DELAY_DAYS,
    REMINDER_MIN_WORDS,
    REVIEW_WINDOW_HOURS,
    SCHEDULER_INTERVAL_MINUTES,
)
from cefr import BANDS, band_index, level_to_cefr
from learning_core_v2.acquisition import (
    LexicalItem,
    ReviewSchedule,
    lexical_item_id,
)
from learning_core_v2.dictionary import DictionaryLookupRequest
from learning_core_v2.goal import GoalReviewPolicy
from learning_core_v2.sentence_mining import SentenceMiningRequest as MiningCoreRequest
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import (
    build_dictionary_enrichment,
    build_sentence_mining,
)
from models import VALID_ENGLISH_LEVELS, UserSettings
from storage import UserStorage, get_storage
from writing_systems import (
    WritingSystemProfile,
    normalize_literacy_stage,
    writing_system_profile,
)

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
    mining_same_level_examples: int = 2
    mining_higher_level_examples: int = 1
    is_onboarded: bool = False
    writing_system: WritingSystemProfile | None = None


class RemindersResponse(BaseModel):
    due_words: int
    due_word_names: list[str] = Field(default_factory=list)
    due_goal: str | None = None
    should_remind: bool
    poll_interval_minutes: int = SCHEDULER_INTERVAL_MINUTES


class KBSummaryResponse(BaseModel):
    learning_count: int
    known_count: int
    goals_count: int
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


class LexicalItemResponse(BaseModel):
    item_id: str
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
    words: list[LexicalItemResponse]


class LexicalItemReviewRequest(BaseModel):
    item_id: str
    rating: str


class AddWordRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=200)


class SentenceMiningRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=100)
    force: bool = False


def _goal_needing_review(storage: UserStorage) -> str | None:
    goals = storage.goals.for_language(storage.settings.target_lang or "en")
    return GoalReviewPolicy().first_due(goals)


async def _dictionary_details(storage: UserStorage, entry) -> dict[str, str]:
    try:
        result = await build_dictionary_enrichment().execute(
            DictionaryLookupRequest(
                term=entry.term,
                learning_language=storage.settings.target_lang,
                native_language=storage.settings.native_lang,
                proficiency=storage.settings.english_level or "intermediate",
                context=entry.latest_context,
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


async def _sentence_mining_card(
    storage: UserStorage,
    entry,
    *,
    level: str,
    higher_level: str,
    same_count: int,
    higher_count: int,
) -> dict:
    try:
        card = await build_sentence_mining().execute(
            MiningCoreRequest(
                term=entry.term,
                known_translation=entry.translation,
                context=entry.latest_context,
                learning_language=storage.settings.target_lang,
                native_language=storage.settings.native_lang,
                learner_cefr=level,
                stretch_cefr=higher_level,
                learner_example_count=same_count,
                stretch_example_count=higher_count,
            )
        )
    except (LanguageProviderError, ValueError) as exc:
        log.warning("core-v2 sentence mining unavailable: %s", exc)
        return {}
    return {
        "examples": [
            {
                "sentence": example.sentence,
                "translation": example.translation,
                "level": example.level,
                "is_higher": example.is_higher,
            }
            for example in card.examples
        ],
        "mnemonic": card.mnemonic,
        "collocations": [
            {"text": item.text, "translation": item.translation}
            for item in card.collocations
        ],
    }


def _due_word_names(storage: UserStorage, limit: int = 8) -> list[str]:
    now = time.time()
    window_seconds = REVIEW_WINDOW_HOURS * 3600
    items = [
        item
        for item in storage.lexicon.all()
        if item.status == "learning"
        and item.schedule.review_count >= 0
        and item.schedule.next_review_at - now <= window_seconds
    ]
    items.sort(
        key=lambda item: (
            item.schedule.next_review_at,
            -item.schedule.review_count,
            item.term.lower(),
        )
    )
    return [item.term for item in items[:limit]]


def _settings_response(storage: UserStorage) -> SettingsResponse:
    s = storage.settings
    language_settings = {
        lang: {
            **prefs,
            "literacy_stage": writing_system_profile(
                s.native_lang,
                lang,
                prefs.get("level", ""),
                prefs.get("literacy_stage", ""),
            ).literacy_stage,
        }
        for lang, prefs in s.language_settings.items()
    }
    language_settings.setdefault(s.target_lang, {
        "level": s.english_level or "",
        "goals": s.goals,
        "prompt": s.general_prompt,
        "literacy_stage": s.literacy_stage,
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
        mining_same_level_examples=s.mining_same_level_examples,
        mining_higher_level_examples=s.mining_higher_level_examples,
        is_onboarded=s.is_onboarded(),
        writing_system=writing_system_profile(
            s.native_lang,
            s.target_lang,
            s.english_level,
            s.literacy_stage,
        ),
    )


def _word_response(item: LexicalItem) -> LexicalItemResponse:
    return LexicalItemResponse(
        item_id=item.item_id,
        name=item.term,
        context=item.latest_context,
        translation=item.translation,
        transcription=item.transcription,
        counter=item.schedule.review_count,
        known=item.status == "known",
        next_review=item.schedule.next_review_at,
        added_at=item.schedule.added_at,
        sentence_mining=(
            SentenceMiningResponse(**item.sentence_mining)
            if item.sentence_mining
            else None
        ),
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
        normalized_settings: dict[str, dict[str, str]] = {}
        for lang, source_prefs in req.language_settings.items():
            prefs = dict(source_prefs)
            profile_level = prefs.get("level", "")
            if profile_level and profile_level not in VALID_ENGLISH_LEVELS:
                raise HTTPException(status_code=400, detail=f"Invalid level for {lang}.")
            profile = writing_system_profile(
                req.native_lang,
                lang,
                profile_level,
                prefs.get("literacy_stage", ""),
            )
            prefs["literacy_stage"] = normalize_literacy_stage(
                prefs.get("literacy_stage", ""), default=profile.literacy_stage
            )
            normalized_settings[lang] = prefs
        language_settings.update(normalized_settings)
    language_settings = {
        lang: prefs for lang, prefs in language_settings.items()
        if lang in target_langs
    }
    language_settings.setdefault(req.target_lang, {
        "level": level or "",
        "goals": req.goals,
        "prompt": req.general_prompt,
        "literacy_stage": storage.settings.literacy_stage,
    })
    for lang in target_langs:
        language_settings.setdefault(
            lang,
            {"level": "", "goals": "", "prompt": "", "literacy_stage": ""},
        )
    for lang, prefs in language_settings.items():
        profile = writing_system_profile(
            req.native_lang,
            lang,
            prefs.get("level", ""),
            prefs.get("literacy_stage", ""),
        )
        prefs["literacy_stage"] = profile.literacy_stage
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
    decayed = storage.lexicon.apply_overdue_decay()
    if decayed:
        storage.save()
        log.info("[reminders] user %r: %d word(s) decayed", username, len(decayed))
    due_words = storage.lexicon.due_count()
    due_word_names = _due_word_names(storage)
    due_goal = _goal_needing_review(storage)
    return RemindersResponse(
        due_words=due_words,
        due_word_names=due_word_names,
        due_goal=due_goal,
        should_remind=due_words >= REMINDER_MIN_WORDS or due_goal is not None,
    )


@router.get("/api/kb_summary", response_model=KBSummaryResponse)
async def api_kb_summary(username: CurrentUser) -> KBSummaryResponse:
    storage = get_storage(username)
    review_counts = db.review_log_counts(username)
    return KBSummaryResponse(
        learning_count=storage.lexicon.learning_count(),
        known_count=storage.lexicon.known_count(),
        goals_count=len(storage.goals),
        **review_counts,
    )


@router.delete("/api/kb_word")
async def api_delete_kb_word(item_id: str, username: CurrentUser) -> dict:
    storage = get_storage(username)
    if not storage.lexicon.remove(item_id):
        raise HTTPException(status_code=404, detail="Lexical item not found.")
    storage.save()
    log.info("[kb_word] deleted item=%s for user=%r", item_id, username)
    return {"ok": True}


@router.get("/api/kb_words", response_model=KBWordsResponse)
async def api_kb_words(username: CurrentUser) -> KBWordsResponse:
    storage = get_storage(username)
    items = sorted(
        (
            item
            for item in storage.lexicon.all()
            if item.language == storage.settings.target_lang
            and item.status in {"learning", "known"}
        ),
        key=lambda item: (item.term.casefold(), item.translation.casefold()),
    )
    return KBWordsResponse(words=[
        LexicalItemResponse(
            item_id=item.item_id,
            name=item.term,
            context=item.latest_context,
            translation=item.translation,
            transcription=item.transcription,
            counter=item.schedule.review_count,
            known=item.status == "known",
            next_review=item.schedule.next_review_at,
            added_at=item.schedule.added_at,
            sentence_mining=(
                SentenceMiningResponse(**item.sentence_mining)
                if item.sentence_mining
                else None
            ),
        )
        for item in items
    ])


@router.post("/api/kb_word", response_model=LexicalItemResponse)
async def api_add_kb_word(req: AddWordRequest, username: CurrentUser) -> LexicalItemResponse:
    """Add a tracked word and synchronously populate its dictionary fields."""
    storage = get_storage(username)
    term = " ".join(req.word.split()).lower()
    existing = storage.lexicon.find_active_term(term, storage.settings.target_lang)
    if existing is not None:
        if not existing.translation or not existing.transcription:
            result = await _dictionary_details(storage, existing)
            if not result.get("translation"):
                raise HTTPException(
                    status_code=502, detail="Could not generate dictionary details."
                )
            existing = replace(
                existing,
                translation=existing.translation or result["translation"],
                transcription=existing.transcription
                or result.get("transcription", ""),
            )
            storage.lexicon.replace(existing)
            storage.save()
        return _word_response(existing)

    draft = LexicalItem(
        item_id="pending",
        term=term,
        language=storage.settings.target_lang,
        translation="",
        status="learning",
    )
    result = await _dictionary_details(storage, draft)
    if not result.get("translation"):
        raise HTTPException(status_code=502, detail="Could not generate dictionary details.")
    now = time.time()
    headword = " ".join((result.get("headword") or term).split()).lower()
    entry = replace(
        draft,
        item_id=lexical_item_id(headword, draft.language, result["translation"]),
        term=headword,
        translation=result["translation"],
        transcription=result.get("transcription", ""),
        schedule=ReviewSchedule(
            review_count=0,
            next_review_at=now + FIRST_REVIEW_DELAY_DAYS * 86400,
            added_at=now,
        ),
    )
    storage.lexicon.append(entry)
    storage.save()
    return _word_response(entry)


@router.get("/api/kb_word_details", response_model=LexicalItemResponse)
async def api_kb_word_details(item_id: str, username: CurrentUser) -> LexicalItemResponse:
    storage = get_storage(username)
    entry = storage.lexicon.find(item_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found.")
    if not entry.translation or not entry.transcription:
        result = await _dictionary_details(storage, entry)
        if not result.get("translation"):
            raise HTTPException(status_code=502, detail="Could not generate dictionary details.")
        entry = replace(
            entry,
            translation=entry.translation or result.get("translation", ""),
            transcription=entry.transcription or result.get("transcription", ""),
        )
        storage.lexicon.replace(entry)
        storage.save()
    return _word_response(entry)


@router.post("/api/kb_word_mine", response_model=LexicalItemResponse)
async def api_mine_kb_word(req: SentenceMiningRequest, username: CurrentUser) -> LexicalItemResponse:
    storage = get_storage(username)
    entry = storage.lexicon.find(req.item_id)
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
        card = await _sentence_mining_card(
            storage,
            entry,
            level=level,
            higher_level=higher_level,
            same_count=same_count,
            higher_count=higher_count,
        )
        if not card.get("examples"):
            raise HTTPException(status_code=503, detail="Could not generate Sentence Mining card.")
        entry = replace(entry, sentence_mining={**card, "config": config})
        storage.lexicon.replace(entry)
        storage.save()

    return _word_response(entry)


@router.post("/api/kb_word_review")
async def api_kb_word_review(req: LexicalItemReviewRequest, username: CurrentUser) -> dict:
    storage = get_storage(username)
    entry = storage.lexicon.find(req.item_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found.")
    outcome = "incorrect" if req.rating == "again" else "correct"
    updated = storage.lexicon.apply_review_result(entry, outcome, task_type="anki")
    storage.save()
    return {"ok": True, "next_review": updated.schedule.next_review_at}
