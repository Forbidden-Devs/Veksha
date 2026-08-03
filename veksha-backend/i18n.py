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
from learning_core_v2.catalog_translation import (
    CatalogEntry,
    CatalogTranslationRequest,
)

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
    "chat_mode_translate": "Translate",
    "chat_explain": "More details",
    "chat_listen": "Listen",
    "immersion_on": "Immersion on",
    "immersion_off": "Immerse page",
    "immersion_hint": "Sprinkle level-appropriate sentences in your target language right into the pages you read.",
    "ci_meter_on": "Reading Coach on",
    "ci_meter_off": "Reading Coach",
    "ci_meter_loading": "Checking readability…",
    "ci_meter_refine": "Refine with AI",
    "ci_meter_badge_known": "{pct}% known · {cefr}",
    "ci_meter_verdict_ideal": "Great i+1 content for you — mostly familiar with a healthy stretch of new words.",
    "ci_meter_verdict_too_easy": "You know this well already — good for fluency practice, but little new vocabulary.",
    "ci_meter_verdict_too_hard": "This may be too difficult right now — expect to look up a lot of words.",
    "ci_meter_verdict_close": "Close to your level.",
    "grammar_memory_title": "Grammar Memory",
    "grammar_memory_on": "Grammar Memory on",
    "grammar_memory_off": "Grammar Memory",
    "grammar_memory_scanning": "Analyzing visible text…",
    "grammar_memory_disable": "Turn off Grammar Memory",
    "grammar_memory_collapse": "Collapse the analysis",
    "grammar_memory_expand": "Show grammar memory",
    "grammar_hint_select": "Select a sentence on the page and press the 🔍 button next to it for a detailed grammar analysis.",
    "grammar_analyze_selection": "Analyze the grammar of the selection",
    "grammar_analysis_loading": "Analyzing the sentence…",
    "grammar_analysis_failed": "Could not analyze the selection. Try again.",
    "grammar_analysis_empty": "No notable grammar found in this selection.",
    "grammar_roles_title": "Sentence roles",
    "grammar_patterns_title": "Grammar in context",
    "grammar_memory_patterns": "Your grammar memory",
    "grammar_memory_loading": "Loading saved patterns…",
    "grammar_memory_empty": "Patterns found while you read will collect here.",
    "grammar_memory_seen": "Seen {n}×",
    "grammar_memory_mastered": "Mark as mastered",
    "grammar_memory_reopen": "Study again",
    "grammar_memory_guide_title": "How Grammar Memory works",
    "grammar_memory_guide_intro": "Grammar Memory turns patterns you encounter while reading into a personal, reusable collection.",
    "grammar_memory_guide_step_1": "Turn on Grammar Memory while reading in your learning language. Veksha highlights sentence roles and detects useful constructions.",
    "grammar_memory_guide_step_2": "Open the page panel to see saved patterns, explanations, real examples, and how often each pattern has appeared.",
    "grammar_memory_guide_step_3": "Mark a pattern as mastered when it feels familiar. You can return it to learning at any time.",
    "grammar_memory_guide_tip": "Select a sentence and use the grammar action to add a focused example to your memory.",
    "grammar_role_subject": "Subject",
    "grammar_role_verb": "Verb",
    "grammar_role_object": "Object",
    "grammar_role_place": "Place",
    "grammar_role_time": "Time",
    "grammar_role_modifier": "Modifier",
    "my_words_add": "Add to dictionary",
    "my_words_added": "Added to dictionary",
    "my_words_add_error": "Could not add the word. Try again.",
    "vocabulary_inbox_title": "From your translations",
    "vocabulary_inbox_empty": "New vocabulary suggestions will appear here.",
    "vocabulary_inbox_seen": "Seen {n}×",
    "vocabulary_inbox_learn": "Learn",
    "vocabulary_inbox_known": "I know it",
    "vocabulary_inbox_ignore": "Ignore",
    "vocabulary_inbox_error": "Could not update this suggestion. Try again.",
    "home_quick_suggested": "Review vocabulary suggestions →",
    "my_words_guide_step_1": "Open your word list and turn tracking on there. Veksha counts words only on pages in your target language.",
    "my_words_guide_step_2": "As you browse, a personal frequency list grows automatically and shows where each word appeared most often.",
    "my_words_guide_step_3": "Add an unfamiliar word to your dictionary with one click, then practise it in training.",
    "my_words_guide_tip": "The tile opens your word list, tracking is controlled inside it, and the question-mark button always opens this guide.",
    # Settings
    "settings_title": "Settings",
    "settings_intro": "Tell us your languages and level so we can pick the right words and difficulty for you.",
    "settings_theme": "Theme",
    "theme_light": "Light",
    "theme_grove": "Colorful",
    "theme_dark": "Dark",
    "settings_display_name": "Your name",
    "settings_native_lang": "Your language",
    "settings_learning_languages": "Languages you study",
    "settings_add_language": "Add a language",
    "settings_remove_language": "Remove language",
    "settings_target_lang": "Active learning language",
    "settings_dual_subtitles": "Dual subtitles",
    "settings_dual_subtitles_desc": "Enable translated subtitles and their playback control on YouTube.",
    "feature_guide_open": "How it works",
    "feature_guide_close": "Got it",
    "reading_coach_guide_title": "How Reading Coach works",
    "reading_coach_guide_intro": "Reading Coach checks a page against the words you know and helps you prepare before you start reading.",
    "reading_coach_guide_step_1": "Open an article in the language you're learning, then turn on Reading Coach from Veksha.",
    "reading_coach_guide_step_2": "Open the page badge to see your current coverage, the most important unfamiliar words, and the projected coverage after learning them.",
    "reading_coach_guide_step_3": "Select the useful blockers and prepare them. Veksha adds enriched suggestions to your Vocabulary Inbox for review.",
    "reading_coach_guide_tip": "Words already being learned or waiting in your Inbox are marked and won't be added twice.",
    "reading_coach_projection": "Learn these words: {before}% → {after}% coverage",
    "reading_coach_obstacles": "Words blocking this page",
    "reading_coach_learning": "learning",
    "reading_coach_inbox": "in inbox",
    "reading_coach_prepare": "Prepare selected words",
    "reading_coach_preparing": "Preparing…",
    "reading_coach_added": "{n} word(s) added to your Inbox",
    "reading_coach_failed": "Could not prepare words",
    "reading_coach_ready": "No high-impact blockers found. Start reading!",
    "dual_subtitles_guide_title": "How dual subtitles work",
    "dual_subtitles_guide_intro": "Dual subtitles add a translation above the original captions while you watch YouTube.",
    "dual_subtitles_guide_step_1": "Open a YouTube video and turn on its original captions.",
    "dual_subtitles_guide_step_2": "Turn on Dual subtitles in Veksha. The translated line appears above the original one.",
    "dual_subtitles_guide_step_3": "Use the globe button beside the captions to hide or show the translation without leaving the video.",
    "dual_subtitles_guide_tip": "Hover over a word in the original captions to highlight the matching word in the translation.",
    "settings_level": "My level",
    "settings_level_placeholder": "Select your level...",
    "settings_goals": "Your goals",
    "settings_goals_placeholder": "e.g. Improve speaking, expand vocabulary, business English...",
    "settings_prompt_label": "General prompt for AI",
    "settings_prompt_placeholder": "e.g. Be supportive, correct my mistakes, explain grammar simply...",
    "settings_mining_title": "Sentence Mining cards",
    "settings_mining_desc": "Choose how many AI examples to generate when you open a saved word.",
    "settings_mining_current": "At my current level",
    "settings_mining_higher": "One level higher",
    "settings_reminder_level": "Reminder intensity",
    "settings_reminder_level_desc": "How insistently Veksha reminds you to train.",
    "settings_reminder_level_1": "Just a notification",
    "settings_reminder_level_2": "Noticeable card",
    "settings_reminder_level_3": "Focus screen + frequent",
    "settings_overseer": "Overseer",
    "settings_overseer_desc": "The close button runs away — finish a training or catch it to dismiss.",
    "settings_focus_guard": "Focus safeguard",
    "settings_focus_guard_desc": "Turn reminders into a full-page decision: start now, snooze for 15 minutes, or intentionally pause for today.",
    "settings_subscription": "Subscription",
    "settings_sub_free": "Free plan",
    "settings_sub_premium": "Premium — active until",
    "settings_sub_premium_active": "Premium — active",
    "settings_sub_desc": "Choose only the paid features you need and see the exact monthly total before payment.",
    "settings_sub_connect": "Choose features",
    "settings_sub_manage": "Change feature selection",
    "settings_sub_err": "Could not open the payment form. Try again later.",
    "settings_promo_label": "Promo code",
    "settings_promo_placeholder": "Enter a promo code",
    "settings_promo_submit": "Redeem",
    "settings_promo_success": "Promo code redeemed — Premium unlocked.",
    "settings_promo_error_invalid": "This promo code doesn't exist.",
    "settings_promo_error_exhausted": "This promo code has already been fully claimed.",
    "settings_promo_error_already_redeemed": "You've already redeemed this promo code.",
    "settings_promo_error_generic": "Could not redeem the promo code. Try again later.",
    "premium_required_title": "Feature not active",
    "premium_required_desc": "{feature} isn't included in your subscription. Would you like to add it?",
    "subscription_title": "Choose your features",
    "subscription_intro_new": "All paid features are selected. Turn off anything you don't need — the total updates immediately.",
    "subscription_intro_manage": "Your active features are selected. Adjust the set and continue to confirm the new subscription.",
    "subscription_intro_add": "The requested feature and your current features are selected. Review the total before paying.",
    "subscription_grammar_desc": "Collects grammar patterns and real examples from the texts you read.",
    "subscription_monthly": "/ month",
    "subscription_total": "Total",
    "subscription_continue": "Continue to payment",
    "subscription_opened": "The secure Telegram payment form has opened in a new tab.",
    "subscription_empty": "Select at least one feature to continue.",
    "subscription_load_error": "Could not load subscription options. Try again later.",
    "subscription_cancel": "Cancel subscription",
    "subscription_cancel_confirm": "Cancel the subscription and turn off all paid features now?",
    "subscription_cancel_error": "Could not cancel the subscription. Try again later.",
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
    "dictionary_search_placeholder": "Search for a word…",
    "dictionary_sort_label": "Sort words",
    "dictionary_sort_az": "A–Z",
    "dictionary_sort_za": "Z–A",
    "dictionary_sort_newest": "Newest first",
    "dictionary_sort_oldest": "Oldest first",
    "dictionary_no_results": "No matching words found.",
    "dictionary_translation": "Translation",
    "dictionary_transcription": "Transcription",
    "dictionary_show_answer": "Show answer",
    "dictionary_again": "Again",
    "dictionary_good": "Good",
    "sentence_mining_title": "AI Sentence Mining card",
    "sentence_mining_loading": "Creating examples, mnemonic and collocations…",
    "sentence_mining_examples": "Examples",
    "sentence_mining_mnemonic": "Mnemonic",
    "sentence_mining_collocations": "Frequent collocations",
    "sentence_mining_regenerate": "Regenerate",
    "sentence_mining_error": "Could not create the AI card.",
    "sentence_mining_level_up": "level up",
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
    "reminder_focus_note": "Choose what happens next so this review does not disappear unnoticed.",
    "reminder_snooze": "Remind me in 15 minutes",
    "reminder_skip_today": "Pause for today",
    # Common
    "app_loading": "Loading...",
    "feature_enabled": "On",
    "feature_disabled": "Off",
    "common_yes": "Yes",
    "common_no": "No",
    # Native language picker (step 1 of onboarding)
    "native_lang_title": "What's your language?",
    "native_lang_subtitle": "We'll show translations and the interface in your language",
    # Target language picker (step 3 of onboarding)
    "target_lang_title": "What do you want to learn?",
    "target_lang_subtitle": "Choose one or more languages you want to study",
    "target_lang_start": "Let's start!",
    "language_search_no_results": "No languages found. Try another name.",
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
    "ocr_capture_hint": "Drag across the text you want to translate.",
    "ocr_recognized_text": "Recognized text",
    "ocr_translate_selection": "Translate selection",
    "ocr_choose_again": "Choose again",
    "ocr_translate_area": "Translate area",
    "ocr_copy_translation": "Copy translation",
    "ocr_translation_copied": "Copied",
    "content_translate": "Translate selection",
    "content_close": "Close",
    "content_translation_failed": "Translation failed. Try again.",
    "content_explanation_failed": "Explanation is unavailable.",
    "content_explain": "More details",
    "content_listen": "Listen",
    "content_breakdown": "Break down",
    "content_edit_text": "Edit text",
    "content_hide_source": "Hide source",
    "content_no_user": "Open the Veksha popup and enter your name first.",
    "content_dualsubs": "Dual subtitles",
    # Quizlet import/export
    "quizlet_loading": "Loading Quizlet data…",
    "quizlet_status_title": "Export status",
    "quizlet_total_words": "Total words",
    "quizlet_exported": "Exported",
    "quizlet_not_exported": "Not exported",
    "quizlet_export_options": "Export options",
    "quizlet_exporting": "Exporting…",
    "quizlet_export_new": "Export new ({n})",
    "quizlet_export_all": "Export all ({n})",
    "quizlet_export_new_hint": "Only words you have not exported yet.",
    "quizlet_export_all_hint": "Every word in your vocabulary.",
    "quizlet_format_hint": "Both options download a CSV file ready for Quizlet.",
    "quizlet_import_title": "Import from Quizlet",
    "quizlet_import_desc": "Upload a Quizlet CSV to add words to your vocabulary. Expected columns: Word, Translation, Context.",
    "quizlet_importing": "Importing…",
    "quizlet_select_csv": "Select CSV file",
    "quizlet_imported": "Imported",
    "quizlet_skipped": "Skipped",
    "quizlet_errors": "Errors ({n})",
    "quizlet_export_success": "Export complete. The file has been downloaded.",
    "quizlet_export_steps_title": "How to export from Quizlet",
    "quizlet_export_step_1": "Open your study set in Quizlet.",
    "quizlet_export_step_2": "Open the three-dot menu (⋮).",
    "quizlet_export_step_3": "Choose Export and select CSV.",
    "quizlet_export_step_4": "Upload the downloaded file here.",
    "quizlet_error_status": "Could not load Quizlet export status.",
    "quizlet_error_export": "Could not export new words.",
    "quizlet_error_export_all": "Could not export the vocabulary.",
    "quizlet_error_csv": "Select a CSV file.",
    "quizlet_error_import": "Could not import this file. Check its format and try again.",
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
    "train_no_words": "📭 No words to train yet. Translate some text first.",
    "train_intro": "🏋️ <b>Training!</b>\n\n<i>(say 'stop' to quit at any time)</i>",
    "train_correct": "✅ Correct!",
    "train_incorrect": "❌ Incorrect.",
    "education_new_topic": "📚 New topic: <b>{name}</b>\n{desc}",
    "education_interrupted": "⏸ Lesson paused, see you next time!",
    "education_no_topics": "📭 No lesson topics yet. Add one from the Topics screen.",
    "training_q_translation": "How do you translate the word **{word}**?",
    "training_q_reverse": "How do you say in English: **{word}**?",
    "training_q_synonym": "Name a synonym for **{word}** in English.",
    "training_q_example": "Write a sentence in English using the word **{word}**.",
    "lesson_no_blocks": "No available blocks for this topic.",
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
        cached = json.loads(path.read_text("utf-8"))
        current_keys = {*UI_STRINGS, *BACKEND_STRINGS, _META_SAME_AS_EN}
        return {key: value for key, value in cached.items() if key in current_keys}
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
    """Serve only current catalogue fields, never obsolete cached UI keys."""
    current_keys = {*UI_STRINGS, *BACKEND_STRINGS}
    return {key: value for key, value in strings.items() if key in current_keys}


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
    from learning_core_v2_adapters.runtime import build_catalog_translator

    try:
        return await build_catalog_translator().execute(
            CatalogTranslationRequest(
                tuple(
                    CatalogEntry(key, value)
                    for key, value in zip(keys, values, strict=True)
                ),
                lang,
            )
        )
    except Exception as err:
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
