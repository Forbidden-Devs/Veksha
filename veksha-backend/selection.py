"""
selection.py — text selection handling in the extension's translation popup.

Each selection goes through llm.translate_selection (mini-Input Processor
for translation): simultaneously gives a translation and classifies
single/not-single (analogous to spec 3.1 — single when action == null).

  single == true:
    - normalized_text — selection restored to dictionary form without
      typos (e.g. "runing" -> "run").
    - patch add_word(value=normalized_text, counter=0) — word is actively
      being studied (user explicitly looked up translation), counter=0
      (not -1, which is for words added "from context").

  single == false:
    - patches built via llm.extract_metadata(text, translation, topic_names)
      (spec 3.2, same as for an expanded phrase).

explain_text() — "More details" button: translation + example/explanation.
"""
from __future__ import annotations

import logging

import llm
from models import Patch
from storage import UserStorage

log = logging.getLogger(__name__)


async def translate_and_update_kb(
    storage: UserStorage,
    text: str,
    source_lang: str,
    target_lang: str,
    bidirectional: bool = False,
) -> dict:
    """
    Translate selected text and update KB with patches (single/not-single).

    Returns:
      {
        "translation": str,
        "detected_source_lang": str | None,
        "single": bool,
        "normalized_text": str,   # only if single == true
      }
    """
    level = storage.settings.english_level or "intermediate"

    if bidirectional:
        source_lang = storage.settings.native_lang or source_lang
        target_lang = storage.settings.target_lang or target_lang

    result = await llm.translate_selection(
        text,
        source_lang,
        target_lang,
        level=level,
        bidirectional=bidirectional,
    )

    if not result["translation"]:
        log.info("[selection] empty translation for text=%r, skipping KB update", text)
        return result

    await update_kb_from_selection(storage, text, result)
    return result


async def update_kb_from_selection(storage: UserStorage, text: str, result: dict) -> None:
    """
    Update KB from the result of translate_selection.
    Called either synchronously (via translate_and_update_kb) or as a
    FastAPI BackgroundTask (from /api/quick_translate).
    """
    if result["single"]:
        normalized = (result.get("normalized_text") or text).strip().lower()
        if not normalized:
            normalized = text.strip().lower()

        existing = storage.find_word(normalized)
        if existing is None:
            log.info("[selection] single=true -> add_word(%r, counter=0)", normalized)
            patch = Patch(type="add_word", value=normalized, context="", counter=0, known=False)
            storage.apply_kb_changes([patch])
        else:
            log.info("[selection] single=true -> word %r already in KB, skipping add_word", normalized)

        result["normalized_text"] = normalized
    else:
        log.info("[selection] single=false -> Extract Metadata")
        topic_names = [t.name for t in storage.lesson_topics]
        patches = await llm.extract_metadata(text, result["translation"], topic_names)
        if patches:
            storage.apply_kb_changes(patches)
        else:
            log.info("[selection] Extract Metadata returned no patches")


async def explain_text(storage: UserStorage, text: str, translation: str) -> str:
    """
    "More details" button: expanded explanation with an example, shown in the
    same popup window.
    """
    level = storage.settings.english_level or "intermediate"
    return await llm.explain_selection(text, translation, level=level)
