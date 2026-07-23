"""
api/debug.py — debug commands (development only; mounted only when
VEKSHA_DEBUG_API is enabled, see main.py).

  POST /api/debug/reset             — wipe the current user's data (KB + history)
  POST /api/debug/simulate-training — mark random words/topic as reviewed
  POST /api/debug/advance-day       — shift all reviews one day closer
"""
from __future__ import annotations

import logging
import random
import time

from fastapi import APIRouter

import db
from auth import CurrentUser
from config import REMINDER_MIN_WORDS, SCHEDULER_INTERVAL_MINUTES
from storage import drop_storage, get_storage

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/debug/reset")
async def api_debug_reset(username: CurrentUser) -> dict:
    """Resets all learning data while preserving the account and token."""
    drop_storage(username)
    db.delete_user_data(username)
    log.info("[debug/reset] user %r: data wiped", username)
    return {"ok": True, "deleted": [username]}


@router.post("/api/debug/simulate-training")
async def api_debug_simulate_training(username: CurrentUser) -> dict:
    """Apply a successful training result to up to 15 random active words and one topic."""
    storage = get_storage(username)
    active_words = [w for w in storage.words if w.known is False or w.known == ""]
    selected_words = random.sample(active_words, min(15, len(active_words)))
    for word in selected_words:
        storage.apply_review_result(word, "correct", task_type="debug_simulate")

    topic_names = sorted(t.name for t in storage.lesson_topics)
    topic_name = random.choice(topic_names) if topic_names else None
    if topic_name:
        lesson_topic = storage.find_lesson_topic(topic_name)
        if lesson_topic:
            lesson_topic.last_reviewed = time.time()
            if lesson_topic.blocks:
                block = random.choice(lesson_topic.blocks)
                block.mastery_score = min(1.0, block.mastery_score * 0.4 + 0.6)

    storage.save()
    log.info(
        "[debug/simulate-training] user=%r words=%d topic=%r",
        username, len(selected_words), topic_name,
    )
    return {
        "ok": True,
        "words_updated": len(selected_words),
        "topic_updated": topic_name,
    }


@router.post("/api/debug/advance-day")
async def api_debug_advance_day(username: CurrentUser) -> dict:
    """Move every scheduled word review one day closer, then return reminder state."""
    from api.settings import _due_word_names, _topic_needing_review

    storage = get_storage(username)
    shifted = 0
    for word in storage.words:
        if word.next_review:
            word.next_review -= 24 * 3600
            # Shift the review history too, so FSRS sees a full day of
            # elapsed time (retrievability drops accordingly).
            if word.last_review:
                word.last_review -= 24 * 3600
            shifted += 1
    storage.save()

    storage.apply_overdue_decay()
    due_words = storage.due_count()
    due_word_names = _due_word_names(storage)
    due_topic = _topic_needing_review(storage)
    reminder = {
        "due_words": due_words,
        "due_word_names": due_word_names,
        "due_topic": due_topic,
        "should_remind": due_words >= REMINDER_MIN_WORDS or due_topic is not None,
        "poll_interval_minutes": SCHEDULER_INTERVAL_MINUTES,
    }
    log.info(
        "[debug/advance-day] user=%r shifted=%d reminder=%s",
        username, shifted, reminder,
    )
    return {"ok": True, "words_shifted": shifted, "reminder": reminder}
