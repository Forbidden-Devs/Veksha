"""
i18n.py — catalogue of all UI strings and server strings for Veksha + LLM-based translation.

UI_STRINGS      — extension UI strings (English base).
BACKEND_STRINGS — server strings (training, lessons, unknown-message replies).

When a new language is selected: /api/i18n/translate sends batches to the LLM in parallel,
the result is saved to data/i18n_{lang}.json and returned to the client for caching.
On next startup the file is loaded directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import config

log = logging.getLogger(__name__)

DATA_DIR = Path(config.DATA_DIR)

# Catalogue seeds shipped with the repo (data/i18n_*.json). When DATA_DIR is
# redirected to a persistent volume, a missing catalogue falls back to the
# seed instead of being regenerated from scratch by the LLM.
_SEED_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# English base — UI strings (mirrored in src/shared/i18n/strings.ts)
# ---------------------------------------------------------------------------

UI_STRINGS: dict[str, str] = {
    # Onboarding (step 2 — username)
    "onboarding_title": "And what's your name?",
    "onboarding_subtitle": "Pick a name to keep your vocabulary and progress. You can change it later in Settings.",
    "onboarding_placeholder": "e.g. yury",
    "onboarding_continue": "Continue",
    "onboarding_loading": "Loading...",
    "onboarding_err_empty": "Please enter a name.",
    "onboarding_err_long": "Name is too long.",
    "onboarding_err_chars": "Use letters, numbers, spaces, - or _ only.",
    "onboarding_err_taken": "This name is already taken.",
    "onboarding_or": "or",
    "onboarding_google": "Continue with Google",
    "onboarding_google_err": "Google sign-in failed. Try again.",
    # Menu
    "menu_title": "Menu",
    "menu_learn": "Start learning",
    "menu_training": "Training",
    "menu_statistics": "Statistics",
    "menu_settings": "Settings",
    "menu_debug": "Debug",
    # Chat
    "chat_reminders": "Reminders",
    "chat_today": "Today",
    "chat_placeholder": "Write a message...",
    "chat_mode_training": "Training",
    "chat_mode_lesson": "Lesson",
    "chat_mode_assistant": "Assistant",
    "chat_mode_translate": "Translate",
    "chat_explain": "More details",
    "chat_listen": "Listen",
    "immersion_on": "Immersion on",
    "immersion_off": "Immerse page",
    "immersion_hint": "Sprinkle level-appropriate sentences in your target language right into the pages you read.",
    # Settings
    "settings_title": "Settings",
    "settings_intro": "Tell us your languages and level so we can pick the right words and difficulty for you.",
    "settings_theme": "Theme",
    "settings_display_name": "Your name",
    "settings_native_lang": "Your language",
    "settings_target_lang": "Active learning language",
    "settings_voice_input": "Voice input",
    "settings_voice_input_desc": "Enable microphone features for this account.",
    "settings_level": "My level",
    "settings_level_placeholder": "Select your level...",
    "settings_goals": "Your goals",
    "settings_goals_placeholder": "e.g. Improve speaking, expand vocabulary, business English...",
    "settings_prompt_label": "General prompt for AI",
    "settings_prompt_placeholder": "e.g. Be supportive, correct my mistakes, explain grammar simply...",
    "settings_reminder_level": "Reminder intensity",
    "settings_reminder_level_desc": "How insistently Veksha reminds you to train.",
    "settings_reminder_level_1": "Just a notification",
    "settings_reminder_level_2": "Pop-up with blur",
    "settings_reminder_level_3": "Blur + frequent",
    "settings_overseer": "Overseer",
    "settings_overseer_desc": "The close button runs away — finish a training or catch it to dismiss.",
    "settings_account": "Account",
    "settings_google_link": "Link Google account",
    "settings_google_linked": "Google account linked",
    "settings_google_link_taken": "This Google account is already linked to another profile.",
    "settings_signout": "Sign out",
    "settings_signout_confirm": "Sign out? Without a linked Google account you won't be able to get back into this profile.",
    "settings_save": "Save",
    "settings_saving": "Saving...",
    "settings_translating": "Translating interface...",
    "settings_err_no_level": "Please select your level.",
    "settings_err_same_lang": "Native and target language must be different.",
    "settings_err_load": "Could not load settings.",
    "settings_err_save": "Could not save settings.",
    # English levels
    "level_beginner": "Beginner (A1)",
    "level_elementary": "Elementary (A2)",
    "level_intermediate": "Intermediate (B1–B2)",
    "level_upper_intermediate": "Upper-Intermediate (B2–C1)",
    "level_advanced": "Advanced (C1–C2)",
    # Statistics
    "stats_title": "Statistics",
    "stats_in_progress": "Words in progress",
    "stats_known": "Words known",
    "stats_topics": "Topics",
    "stats_ready": "Ready to review now",
    "stats_anki_reviews": "Card reviews",
    "stats_training_reviews": "Training answers",
    "dictionary_title": "Dictionary",
    "dictionary_cards": "Practice cards",
    "dictionary_translation": "Translation",
    "dictionary_transcription": "Transcription",
    "dictionary_show_answer": "Show answer",
    "dictionary_again": "Again",
    "dictionary_good": "Good",
    "stats_review_today": "review today",
    "stats_review_in_days": "review in {n}d",
    "stats_review_overdue": "review overdue",
    # Reminders
    "reminder_title": "Time to practice!",
    "reminder_subtitle_default": "You have words to review.",
    "reminder_words": "{n} word(s) to review",
    "reminder_topic": "unfinished topic",
    "reminder_have": "You have {items}.",
    "reminder_start": "Start training",
    "reminder_dismiss": "Dismiss reminder",
    # Common
    "app_loading": "Loading...",
    # Native language picker (step 1 of onboarding)
    "native_lang_title": "What's your language?",
    "native_lang_subtitle": "We'll show translations and the interface in your language",
    # Target language picker (step 3 of onboarding)
    "target_lang_title": "What do you want to learn?",
    "target_lang_subtitle": "Choose one or more languages you want to study",
    "target_lang_start": "Let's start!",
    # Level setup (step 4 of onboarding)
    "level_setup_title": "Almost there!",
    "level_setup_subtitle": "Tell us your level so we can pick the right tasks for you.",
    "level_setup_optional": "optional",
    # Training window
    "training_title": "Training",
    "training_loading": "Loading task...",
    "training_done": "Session complete — {n} words done!",
    "training_close": "Close",
    "training_check": "Check",
    "training_checking": "Checking...",
    "training_next": "Next →",
    "training_placeholder": "Your answer...",
    "training_err_connect": "Could not connect to server.",
    "training_err_lost": "Connection lost.",
    "training_err_server": "Server error",
    # Mic button
    "mic_stop": "Stop recording",
    "mic_recognizing": "Recognizing...",
    "mic_voice_input": "Voice input",
    "mic_err_none": "Nothing recognized — try again",
    "mic_err_service": "STT service unavailable",
    "mic_err_denied": "Microphone access denied",
    "mic_err_generic": "Microphone error",
    # Lesson window
    "lesson_preparing": "Preparing material...",
    "lesson_loading_question": "Loading question...",
    "lesson_done": "Session complete — {n} question(s) done!",
    "lesson_err_connect": "Could not connect to server.",
    "lesson_err_lost": "Connection lost.",
    "lesson_err_server": "Server error",
    "lesson_err_no_topic": "Topic not specified.",
    # Topic picker
    "topics_loading": "Loading topics...",
    "topics_empty": "No topics yet. Add your first topic below.",
    "topics_blocks": "{n} block(s)",
    "topics_placeholder": 'New topic (e.g. "English grammar")...',
    "topics_add": "Add",
    # Content script (translation popup on page)
    "content_translating": "Translating...",
    "content_explain": "More details",
    "content_listen": "Listen",
    "content_breakdown": "Break down",
    "content_edit_text": "Edit text",
    "content_hide_source": "Hide source",
    "content_no_user": "Open the Veksha popup and enter your name first.",
    "content_dualsubs": "Dual subtitles",
    # Debug
    "debug_title": "Debug",
    "debug_user": "User",
    "debug_backend": "Backend",
    "debug_browser_lang": "Browser lang",
    "debug_all_langs": "All langs",
    "debug_commands": "Commands",
    "debug_simulate_training_name": "Simulate completed training",
    "debug_simulate_training_desc": "Advances 15 random words and one random topic as if training was completed.",
    "debug_advance_day_name": "Move to tomorrow",
    "debug_advance_day_desc": "Moves all word review dates one day back and triggers a reminder.",
    "debug_reset_name": "Reset user data",
    "debug_reset_desc": "Deletes all KB, session and settings on the server, then clears local storage. Registration starts from scratch.",
    "debug_reset_confirm": "Reset ALL data for \"{username}\"? This cannot be undone.",
    "debug_run": "Run",
    "debug_reloading": "Reloading…",
}

# ---------------------------------------------------------------------------
# Backend strings — generated by server code (not LLM), need translation too
# ---------------------------------------------------------------------------

BACKEND_STRINGS: dict[str, str] = {
    "train_stopped": "🏁 Training stopped. Words done: {n}.",
    "train_limit_reached": "🏁 Training limit reached ({limit} words). Great job!",
    "train_all_done": "🎉 All words for today reviewed! Done: {n}.",
    "train_all_known": "✅ All words are already learned. Great job!",
    "train_no_words": "📭 No words to train yet. Translate some text first or ask me to add words.",
    "train_intro": "🏋️ <b>Training!</b>\n\n<i>(say 'stop' to quit at any time)</i>",
    "train_correct": "✅ Correct!",
    "train_incorrect": "❌ Incorrect.",
    "education_new_topic": "📚 New topic: <b>{name}</b>\n{desc}",
    "education_interrupted": "⏸ Lesson paused, see you next time!",
    "education_no_topics": "📭 No lesson topics yet and I couldn't create one.\n\nTry saying: 'Let's study travel vocabulary'.",
    "unknown_msg": "🤔 I didn't understand. Type a word or phrase — I'll translate it. Or say 'training' / 'lesson'.",
    "training_q_translation": "How do you translate the word **{word}**?",
    "training_q_reverse": "How do you say in English: **{word}**?",
    "training_q_synonym": "Name a synonym for **{word}** in English.",
    "training_q_example": "Write a sentence in English using the word **{word}**.",
    "lesson_no_blocks": "No available blocks for this topic.",
    # edit_knowledge_base notifications
    "edit_kb_words_added": "✅ Added {n} word(s) to your vocabulary.",
    "edit_kb_topics_added": "📚 Added {n} lesson topic(s): {topics}.",
    "edit_kb_word_not_found": "Could not find word \"{value}\" in your vocabulary.",
    "edit_kb_topic_not_found": "Could not find topic \"{value}\".",
    "edit_kb_word_known_not_found": "Could not find word \"{value}\" to mark as learned.",
}

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_BATCH_SIZE = 20

# Meta key inside a catalogue file: keys whose correct translation is
# identical to the English source ("Debug", brand names, …). Without this
# marker such keys look permanently untranslated and would be re-sent to the
# LLM on every startup and catalogue request.
_META_SAME_AS_EN = "__same_as_en__"

# Auto-fill attempts per language are rate-limited in-process, so a dead LLM
# key (quota, network) doesn't get hammered by every startup task and
# catalogue request.
_ENSURE_RETRY_SECONDS = 600.0
_ensure_last_attempt: dict[str, float] = {}


def _cache_path(lang: str) -> Path:
    return DATA_DIR / f"i18n_{lang}.json"


def known_langs() -> set[str]:
    """Languages that have a catalogue in the data dir or shipped as a seed."""
    langs: set[str] = set()
    for d in (DATA_DIR, _SEED_DIR):
        for path in d.glob("i18n_*.json"):
            langs.add(path.stem[len("i18n_"):])
    return langs


def load_cached(lang: str) -> dict[str, str] | None:
    if lang == "en":
        return {**UI_STRINGS, **BACKEND_STRINGS}
    path = _cache_path(lang)
    if not path.exists():
        seed = _SEED_DIR / f"i18n_{lang}.json"
        if seed != path and seed.exists():
            path = seed
        else:
            return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        log.exception("[i18n] Failed to read cache for lang=%r", lang)
        return None


def save_cache(lang: str, strings: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(lang).write_text(json.dumps(strings, ensure_ascii=False, indent=2), "utf-8")


def untranslated_strings(lang: str, cached: dict[str, str] | None) -> dict[str, str]:
    """Return catalogue fields that are absent, empty, or still contain the English source.

    Keys listed in the __same_as_en__ meta entry are trusted: the LLM already
    returned the English text as the correct translation for them.
    """
    if lang == "en":
        return {}

    cached = cached or {}
    same_as_en = set(cached.get(_META_SAME_AS_EN) or [])
    all_strings = {**UI_STRINGS, **BACKEND_STRINGS}
    return {
        key: english
        for key, english in all_strings.items()
        if key not in same_as_en
        and (
            not isinstance(cached.get(key), str)
            or not cached[key].strip()
            or cached[key].strip() == english.strip()
        )
    }


def merge_translations(cached: dict, translated: dict[str, str]) -> dict:
    """Merge fresh LLM output into a cached catalogue, maintaining the
    __same_as_en__ meta entry for keys the LLM translated to the English
    source verbatim (so they are not retried forever)."""
    all_strings = {**UI_STRINGS, **BACKEND_STRINGS}
    same_as_en = set(cached.get(_META_SAME_AS_EN) or [])
    for key, value in translated.items():
        english = all_strings.get(key)
        if english is not None and value.strip() == english.strip():
            same_as_en.add(key)
        else:
            same_as_en.discard(key)
    merged = {**cached, **translated}
    if same_as_en:
        merged[_META_SAME_AS_EN] = sorted(same_as_en)
    else:
        merged.pop(_META_SAME_AS_EN, None)
    return merged


def public_catalog(strings: dict) -> dict[str, str]:
    """Catalogue as served to clients — meta entries stripped."""
    return {k: v for k, v in strings.items() if not k.startswith("__")}


def get_string(key: str, native_lang: str, **kwargs: object) -> str:
    """Get a BACKEND_STRINGS entry in the user's language, with template substitution."""
    all_strings: dict[str, str] | None = None
    if native_lang and native_lang != "en":
        all_strings = load_cached(native_lang)
    if all_strings is None:
        all_strings = BACKEND_STRINGS
    text = all_strings.get(key) or BACKEND_STRINGS.get(key, key)
    if kwargs:
        for k, v in kwargs.items():
            text = text.replace(f"{{{k}}}", str(v))
    return text


# ---------------------------------------------------------------------------
# LLM batch translation
# ---------------------------------------------------------------------------

async def _translate_batch(keys: list[str], values: list[str], lang: str) -> dict[str, str]:
    from llm._base import _call as _llm_call  # local import — avoids module-level circular dependency

    pairs = "\n".join(f'"{k}": "{v}"' for k, v in zip(keys, values))
    system = (
        f"You are a professional UI/UX and app translator. "
        f"Translate the following English strings into {lang}. "
        f"Return ONLY a valid JSON object with the exact same keys and translated values. "
        f"Rules: keep placeholders {{n}}, {{items}}, {{name}}, {{desc}}, {{limit}} exactly as-is; "
        f"use natural friendly tone; keep labels short; "
        f"do NOT translate: Veksha, AI, KB, e.g., A1, B1, B2, C1, C2."
    )
    user = f"Translate to {lang}:\n{{{{\n{pairs}\n}}}}"

    try:
        raw = await _llm_call(
            system=system,
            user=user,
            max_tokens=1500,
            temp=0.1,
            json_mode=True,
            call_name=f"i18n_{lang}",
        )
        data = json.loads(raw)
        return {k: str(v) for k, v in data.items() if k in keys}
    except Exception as err:
        # llm._base already logged the full request failure; one line is enough here.
        log.warning("[i18n] batch translate failed for lang=%r: %s", lang, err)
        return {}


async def translate_strings(lang: str, strings: dict[str, str]) -> dict[str, str]:
    """Translate an arbitrary subset of strings to lang (used for filling missing keys)."""
    if not strings:
        return {}
    keys = list(strings.keys())
    values = list(strings.values())
    batches = [
        (keys[i: i + _BATCH_SIZE], values[i: i + _BATCH_SIZE])
        for i in range(0, len(keys), _BATCH_SIZE)
    ]
    results = await asyncio.gather(
        *[_translate_batch(k, v, lang) for k, v in batches]
    )
    merged: dict[str, str] = {}
    for r in results:
        if isinstance(r, dict):
            merged.update(r)
    return merged


async def ensure_cache_complete(lang: str) -> None:
    """Translate every catalogue field that is missing, empty, or still English.

    Rate-limited per language: when the LLM is unavailable (dead key, quota),
    startup tasks and catalogue requests don't retry more than once per
    _ENSURE_RETRY_SECONDS.
    """
    if lang == "en":
        return
    cached = load_cached(lang) or {}
    missing = untranslated_strings(lang, cached)
    if not missing:
        return

    now = asyncio.get_running_loop().time()
    last = _ensure_last_attempt.get(lang)
    if last is not None and now - last < _ENSURE_RETRY_SECONDS:
        return
    _ensure_last_attempt[lang] = now

    log.info("[i18n] translating %d incomplete fields for lang=%r", len(missing), lang)
    translated = await translate_strings(lang, missing)
    if not translated:
        return  # LLM unavailable — leave the cache as is, retry after backoff
    save_cache(lang, merge_translations(cached, translated))


async def generate_translation(lang: str) -> dict[str, str]:
    """
    Translate all UI_STRINGS + BACKEND_STRINGS to lang in parallel batches.
    Missing keys fall back to English.
    """
    all_strings = {**UI_STRINGS, **BACKEND_STRINGS}
    keys = list(all_strings.keys())
    values = list(all_strings.values())

    batches = [
        (keys[i: i + _BATCH_SIZE], values[i: i + _BATCH_SIZE])
        for i in range(0, len(keys), _BATCH_SIZE)
    ]

    results = await asyncio.gather(
        *[_translate_batch(k, v, lang) for k, v in batches]
    )

    merged: dict[str, str] = {}
    for r in results:
        if isinstance(r, dict):
            merged.update(r)

    return merged
