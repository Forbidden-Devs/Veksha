"""
lesson.py — business logic for topic-based learning in the browser extension.

Block generation flow:
  1. generate_block_content  → draft content
  2. review_block_content    → "good" | "revise" | "words_only"
     "good"       → accept, store as content_json
     "revise"     → regenerate with feedback (smart model), review once more
                    still "revise" → fall back to "words_only"
     "words_only" → mark block as skipped, add fallback_words to KB
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from llm.lesson import (
    check_lesson_answer,
    generate_block_content,
    generate_lesson_question,
    review_block_content,
    suggest_block_names,
)
from models import LessonBlock, LessonQA, LessonTopic, Patch
from storage import UserStorage

log = logging.getLogger(__name__)

QUESTIONS_PER_SESSION = 6
BLOCKS_PER_SESSION = 2
QUESTIONS_PER_BLOCK = QUESTIONS_PER_SESSION // BLOCKS_PER_SESSION
MASTERY_THRESHOLD = 0.7
MAX_BLOCKS_PER_TOPIC = 10

_SKIPPED_MARKER = {"__skipped__": True}


def _block_has_content(block: LessonBlock) -> bool:
    """True if block has real (non-skipped) content."""
    if not block.content_json:
        return False
    try:
        return not json.loads(block.content_json).get("__skipped__", False)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Topic list
# ---------------------------------------------------------------------------

def list_topics(storage: UserStorage) -> list[dict]:
    result = []
    for t in storage.lesson_topics:
        result.append({
            "name": t.name,
            "block_count": len([b for b in t.blocks if _block_has_content(b)]),
            "mastery": round(t.avg_mastery(), 2),
            "last_reviewed": t.last_reviewed,
        })
    return result


def create_topic(storage: UserStorage, name: str) -> LessonTopic:
    existing = storage.find_lesson_topic(name)
    if existing:
        return existing
    topic = LessonTopic(name=name)
    storage.lesson_topics.append(topic)
    storage.save()
    log.info("[create_topic] created %r for user %r", name, storage.username)
    return topic


# ---------------------------------------------------------------------------
# Session block selection + content generation
# ---------------------------------------------------------------------------

async def _ensure_content(
    topic: LessonTopic,
    block: LessonBlock,
    level: str,
    goals: str,
    native_lang: str,
    target_lang: str,
    storage: UserStorage,
) -> None:
    """
    Generate and validate content for a block.
    On "words_only" verdict: marks block as skipped and adds fallback words to KB.
    """
    if block.content_json:
        return

    all_names = [b.name for b in topic.blocks]

    # Attempt 1: generate
    content = await generate_block_content(
        topic.name, block.name, all_names, level,
        native_lang=native_lang, target_lang=target_lang,
    )

    review = await review_block_content(
        content, topic.name, block.name, level, goals,
        native_lang=native_lang, target_lang=target_lang,
    )
    log.info("[ensure_content] block=%r first_review=%s", block.name, review["verdict"])

    if review["verdict"] == "revise":
        # Attempt 2: regenerate with smart model + feedback
        content = await generate_block_content(
            topic.name, block.name, all_names, level,
            native_lang=native_lang, target_lang=target_lang,
            revision_feedback=review["feedback"],
        )
        review = await review_block_content(
            content, topic.name, block.name, level, goals,
            native_lang=native_lang, target_lang=target_lang,
        )
        log.info("[ensure_content] block=%r second_review=%s", block.name, review["verdict"])

    if review["verdict"] == "words_only":
        log.info(
            "[ensure_content] block=%r -> words_only: %s (words=%s)",
            block.name, review["feedback"], review["fallback_words"],
        )
        block.content_json = json.dumps(_SKIPPED_MARKER, ensure_ascii=False)
        # Add fallback words to vocabulary
        if review["fallback_words"]:
            patches = [
                Patch(type="add_word", value=w, counter=-1, known=False)
                for w in review["fallback_words"]
            ]
            storage.apply_kb_changes(patches)
        return

    # "good" (or accepted after review failure)
    block.content_json = json.dumps(content, ensure_ascii=False)
    log.info("[ensure_content] block=%r accepted", block.name)


async def _add_new_blocks(
    topic: LessonTopic,
    count: int,
    level: str,
    goals: str,
    native_lang: str,
    target_lang: str,
    storage: UserStorage,
) -> list[LessonBlock]:
    """Ask LLM for new block names, generate + validate their content."""
    existing_names = [b.name for b in topic.blocks]
    new_names = await suggest_block_names(
        topic.name, existing_names, level,
        count=count, native_lang=native_lang, target_lang=target_lang,
    )
    if not new_names:
        topic.is_complete = True
        return []

    new_blocks = [LessonBlock(name=name) for name in new_names]
    topic.blocks.extend(new_blocks)

    await asyncio.gather(*[
        _ensure_content(topic, b, level, goals, native_lang, target_lang, storage)
        for b in new_blocks
    ])

    if len(topic.blocks) >= MAX_BLOCKS_PER_TOPIC or len(new_names) < count:
        topic.is_complete = True

    return [b for b in new_blocks if _block_has_content(b)]


async def select_session_blocks(
    topic: LessonTopic,
    level: str,
    goals: str = "",
    native_lang: str = "en",
    target_lang: str = "en",
    storage: UserStorage | None = None,
) -> list[LessonBlock]:
    """
    Select blocks for the current session:
    1. Take blocks with mastery < MASTERY_THRESHOLD (worst first).
    2. If none and topic not complete — add new blocks (with review loop).
    3. If topic complete — re-use lowest-mastery blocks.
    """
    ready = [b for b in topic.blocks if _block_has_content(b)]
    unmastered = sorted(
        [b for b in ready if b.mastery_score < MASTERY_THRESHOLD],
        key=lambda b: b.mastery_score,
    )

    if len(unmastered) >= BLOCKS_PER_SESSION:
        return unmastered[:BLOCKS_PER_SESSION]

    needed = BLOCKS_PER_SESSION - len(unmastered)
    selected = list(unmastered)

    if not topic.is_complete and len(topic.blocks) < MAX_BLOCKS_PER_TOPIC and storage:
        new_blocks = await _add_new_blocks(
            topic, needed, level, goals, native_lang, target_lang, storage,
        )
        selected.extend(new_blocks[:needed])
    elif ready:
        mastered = sorted([b for b in ready if b not in selected], key=lambda b: b.mastery_score)
        selected.extend(mastered[:needed])

    if not selected and ready:
        selected = sorted(ready, key=lambda b: b.mastery_score)[:BLOCKS_PER_SESSION]

    return selected[:BLOCKS_PER_SESSION]


# ---------------------------------------------------------------------------
# Question order — block interleaving
# ---------------------------------------------------------------------------

def make_question_plan(blocks: list[LessonBlock]) -> list[str]:
    """Interleave blocks: [A, B, A, B, A, B] for better retention."""
    plan = []
    n = len(blocks)
    for i in range(QUESTIONS_PER_SESSION):
        plan.append(blocks[i % n].name)
    return plan


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

async def generate_question(
    topic: LessonTopic,
    block: LessonBlock,
    session_history: list[str],
    level: str,
    native_lang: str = "en",
    target_lang: str = "en",
) -> dict:
    content = json.loads(block.content_json) if block.content_json else {}
    question_text = await generate_lesson_question(
        topic=topic.name,
        block_name=block.name,
        content=content,
        history=session_history,
        level=level,
        native_lang=native_lang,
        target_lang=target_lang,
    )
    return {
        "question_id": str(uuid.uuid4()),
        "block_name": block.name,
        "question": question_text,
    }


# ---------------------------------------------------------------------------
# Answer checking
# ---------------------------------------------------------------------------

async def check_answer(
    topic_name: str,
    block_name: str,
    question: str,
    answer: str,
    level: str,
    native_lang: str = "en",
    target_lang: str = "en",
) -> dict:
    """Returns {"outcome", "feedback", "update_kb"}."""
    result = await check_lesson_answer(
        topic_name, block_name, question, answer, level,
        native_lang=native_lang, target_lang=target_lang,
    )
    result["update_kb"] = result["outcome"] != "garbage"
    return result


# ---------------------------------------------------------------------------
# Mastery update after session
# ---------------------------------------------------------------------------

def update_mastery(block: LessonBlock, outcomes: list[str]) -> None:
    if not outcomes:
        return
    session_score = sum(
        1.0 if o == "correct" else 0.5 if o == "vague" else 0.0
        for o in outcomes
    ) / len(outcomes)
    block.mastery_score = min(1.0, block.mastery_score * 0.4 + session_score * 0.6)
    log.info(
        "[update_mastery] block=%r outcomes=%s -> mastery=%.2f",
        block.name, outcomes, block.mastery_score,
    )


def apply_session_results(
    topic: LessonTopic,
    results_by_block: dict[str, list[str]],
    qa_by_block: dict[str, list[tuple[str, str]]],
) -> None:
    for block_name, outcomes in results_by_block.items():
        block = topic.find_block(block_name)
        if not block:
            continue
        update_mastery(block, outcomes)
        for question, outcome in qa_by_block.get(block_name, []):
            if outcome != "garbage":
                block.history.append(LessonQA(question=question, outcome=outcome))
    topic.last_reviewed = time.time()
