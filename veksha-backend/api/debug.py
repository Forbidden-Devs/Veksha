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
from dataclasses import replace

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
    active_items = [
        item for item in storage.lexicon.all() if item.status == "learning"
    ]
    selected_items = random.sample(active_items, min(15, len(active_items)))
    for item in selected_items:
        storage.lexicon.apply_review_result(item, "correct", task_type="debug_simulate")

    topic_names = sorted(t.name for t in storage.lessons.topics())
    topic_name = random.choice(topic_names) if topic_names else None
    if topic_name:
        lesson_topic = storage.lessons.find(topic_name)
        if lesson_topic:
            units = list(lesson_topic.units)
            if units:
                index = random.randrange(len(units))
                units[index] = replace(
                    units[index], mastery=min(1.0, units[index].mastery * 0.4 + 0.6)
                )
            storage.lessons.put(
                replace(lesson_topic, units=tuple(units), last_reviewed_at=time.time())
            )

    storage.save()
    log.info(
        "[debug/simulate-training] user=%r words=%d topic=%r",
        username, len(selected_items), topic_name,
    )
    return {
        "ok": True,
        "words_updated": len(selected_items),
        "topic_updated": topic_name,
    }


@router.post("/api/debug/advance-day")
async def api_debug_advance_day(username: CurrentUser) -> dict:
    """Move every scheduled word review one day closer, then return reminder state."""
    from api.settings import _due_word_names, _topic_needing_review

    storage = get_storage(username)
    shifted = 0
    for item in storage.lexicon.all():
        schedule = item.schedule
        if schedule.next_review_at:
            storage.lexicon.replace(
                replace(
                    item,
                    schedule=replace(
                        schedule,
                        next_review_at=schedule.next_review_at - 24 * 3600,
                        last_review_at=(
                            schedule.last_review_at - 24 * 3600
                            if schedule.last_review_at
                            else 0.0
                        ),
                    ),
                )
            )
            shifted += 1
    storage.save()

    if storage.lexicon.apply_overdue_decay():
        storage.save()
    due_words = storage.lexicon.due_count()
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
