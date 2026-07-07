"""
pipeline.py — main message processing pipeline.

User message → Input Processor → {action, value, kb_request}

  action == null  (translate / answer):
    value → user

  action == "edit_knowledge_base":
    value (reply) → user immediately
    kb_request → Update Knowledge Base (LLM) → apply_kb_changes
    create lesson_topics for any add_topic patches
    summary notification → user
"""
from __future__ import annotations

import logging

import i18n
import llm
from models import Patch
from storage import UserStorage

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

class PipelineResult:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def add(self, text: str) -> None:
        if text:
            self.messages.append(text)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def process_message(storage: UserStorage, user_message: str, context: str) -> PipelineResult:
    nl = storage.settings.native_lang or "en"
    log.info("[pipeline] === processing message=%r (username=%r) ===", user_message, storage.username)
    result = PipelineResult()

    s = storage.settings
    processor = await llm.input_processor(
        user_message,
        context,
        native_lang=nl,
        target_lang=s.target_lang or "en",
        english_level=s.english_level or "",
        goals=s.goals or "",
        general_prompt=s.general_prompt or "",
    )

    if processor.action is None:
        log.info("[pipeline] action=None (translate/answer)")
        result.add(processor.value)
    elif processor.action == "edit_knowledge_base":
        log.info("[pipeline] action=edit_knowledge_base")
        await _handle_edit_kb(storage, user_message, processor, result, nl)
    else:
        log.warning("[pipeline] unexpected action: %r", processor.action)
        result.add(processor.value or user_message)

    log.info("[pipeline] === done: messages=%d ===", len(result.messages))
    return result


# ---------------------------------------------------------------------------
# action == "edit_knowledge_base"
# ---------------------------------------------------------------------------

async def _handle_edit_kb(
    storage: UserStorage, user_message: str, processor, result: PipelineResult, native_lang: str
) -> None:
    # Step 1: show user-facing reply immediately
    if processor.value:
        result.add(processor.value)

    # Step 2: build and apply patches using the LLM-generated kb_request
    kb_input = processor.kb_request or user_message
    log.info("[pipeline] edit_kb: kb_input=%r", kb_input)
    topic_names = [t.name for t in storage.lesson_topics]
    word_names = [w.name for w in storage.words]
    patches = await llm.update_knowledge_base(
        kb_input, topic_names, word_names,
        english_level=storage.settings.english_level or "",
        target_lang=storage.settings.target_lang or "en",
    )
    notes, words_added, topics_added = await _apply_patches_with_matching(storage, patches, native_lang)

    # Step 3: error notes (word/topic not found for delete/mark_known)
    for note in notes:
        result.add(note)

    # Step 4: summary notification
    summary_parts = []
    if words_added:
        summary_parts.append(i18n.get_string("edit_kb_words_added", native_lang, n=len(words_added)))
    if topics_added:
        summary_parts.append(i18n.get_string("edit_kb_topics_added", native_lang, n=len(topics_added), topics=", ".join(topics_added)))
    if summary_parts:
        result.add("\n".join(summary_parts))

    log.info("[pipeline] edit_kb done, words_added=%s topics_added=%s notes=%s", words_added, topics_added, notes)


async def _apply_patches_with_matching(
    storage: UserStorage, patches: list[Patch], native_lang: str
) -> tuple[list[str], list[str], list[str]]:
    """
    Spec 3.4: for delete_word/delete_topic/mark_known — LLM candidate matching.
    Returns (notes, words_added, topics_added).
    """
    resolved: list[Patch] = []
    notes: list[str] = []
    words_added: list[str] = []
    topics_added: list[str] = []

    for patch in patches:
        if patch.type == "delete_word":
            candidates = [w.name for w in storage.candidates_for_delete_word(patch.value)]
            log.info("[pipeline] delete_word %r -> candidates=%s", patch.value, candidates)
            match = await llm.match_delete_candidate(patch.value, candidates)
            if match is None:
                notes.append(i18n.get_string("edit_kb_word_not_found", native_lang, value=patch.value))
                continue
            resolved.append(Patch(type="delete_word", value=match))

        elif patch.type == "delete_topic":
            candidates = [t.name for t in storage.candidates_for_delete_topic(patch.value)]
            log.info("[pipeline] delete_topic %r -> candidates=%s", patch.value, candidates)
            match = await llm.match_delete_candidate(patch.value, candidates)
            if match is None:
                notes.append(i18n.get_string("edit_kb_topic_not_found", native_lang, value=patch.value))
                continue
            resolved.append(Patch(type="delete_topic", value=match))

        elif patch.type == "mark_known":
            candidates = [w.name for w in storage.candidates_for_delete_word(patch.value)]
            log.info("[pipeline] mark_known %r -> candidates=%s", patch.value, candidates)
            match = await llm.match_delete_candidate(patch.value, candidates)
            if match is None:
                notes.append(i18n.get_string("edit_kb_word_known_not_found", native_lang, value=patch.value))
                continue
            resolved.append(Patch(type="mark_known", value=match))

        elif patch.type == "add_word":
            resolved.append(patch)
            words_added.append(patch.value)

        elif patch.type == "add_topic":
            resolved.append(patch)
            topics_added.append(patch.value)

        else:
            resolved.append(patch)

    if resolved:
        log.info("[pipeline] applying %d resolved patch(es): %s", len(resolved), [(p.type, p.value) for p in resolved])
        apply_notes = storage.apply_kb_changes(resolved)
        notes.extend(apply_notes)

    return notes, words_added, topics_added
