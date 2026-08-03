"""Training HTTP and WebSocket adapters for the rewritten practice core."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import db
from auth import CurrentUser, ws_current_user
from config import REVIEW_WINDOW_HOURS
from learning_core_v2.practice import AnswerCheckRequest, PracticeQueue, PracticeTask
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.practice import LexiconPracticeRepository
from learning_core_v2_adapters.runtime import build_practice_services
from storage import get_storage


log = logging.getLogger(__name__)
router = APIRouter()
MAX_SESSION_TASKS = 10


class TrainingInitResponse(BaseModel):
    available_words: int


class TrainingValidateRequest(BaseModel):
    item_ids: list[str]


class TrainingValidateResponse(BaseModel):
    valid: list[str]


class ReviewLogEntry(BaseModel):
    item_id: str | None = None
    word: str
    ts: float
    rating: int
    outcome: str
    task_type: str
    elapsed_days: float
    scheduled_days: float
    stability: float
    difficulty: float
    retrievability: Optional[float]


class ReviewLogResponse(BaseModel):
    reviews: list[ReviewLogEntry]


def _queue() -> PracticeQueue:
    return PracticeQueue(REVIEW_WINDOW_HOURS * 3600)


@router.get("/api/training/init", response_model=TrainingInitResponse)
async def training_init(username: CurrentUser) -> TrainingInitResponse:
    storage = get_storage(username)
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)
    available = _queue().available(
        repository.items(),
        learning_language=storage.settings.target_lang,
        now=time.time(),
    )
    return TrainingInitResponse(available_words=len(available))


@router.post("/api/training/validate", response_model=TrainingValidateResponse)
async def training_validate(
    req: TrainingValidateRequest, username: CurrentUser
) -> TrainingValidateResponse:
    storage = get_storage(username)
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)
    return TrainingValidateResponse(
        valid=[item_id for item_id in req.item_ids if repository.contains(item_id)]
    )


@router.get("/api/training/review_log", response_model=ReviewLogResponse)
async def training_review_log(
    username: CurrentUser,
    word: Optional[str] = None,
    item_id: Optional[str] = None,
    limit: int = 50,
) -> ReviewLogResponse:
    rows = db.review_log_recent(
        username, word=word, lexical_item_id=item_id, limit=limit
    )
    return ReviewLogResponse(reviews=[ReviewLogEntry(**row) for row in rows])


@router.websocket("/api/training/ws")
async def training_ws(websocket: WebSocket) -> None:
    username = await ws_current_user(websocket)
    if username is None:
        return

    storage = get_storage(username)
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)
    task_builder, answer_checker = build_practice_services()
    queue = _queue()
    proficiency = storage.settings.english_level or "intermediate"
    native_language = storage.settings.native_lang or "en"
    learning_language = storage.settings.target_lang or "en"
    used_items: set[str] = set()
    active_tasks: dict[str, PracticeTask] = {}
    generated_tasks = 0

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid message."})
                continue

            message_type = message.get("type")
            if message_type == "init":
                used_items.update(str(value) for value in message.get("exclude", []))

            elif message_type == "request_task":
                if generated_tasks >= MAX_SESSION_TASKS:
                    await websocket.send_json({"type": "done"})
                    continue
                available = queue.available(
                    repository.items(),
                    learning_language=learning_language,
                    now=time.time(),
                    excluded=used_items,
                )
                if not available:
                    await websocket.send_json({"type": "done"})
                    continue

                item = available[0]
                used_items.add(item.item_id)
                try:
                    task = await task_builder.execute(
                        item,
                        proficiency=proficiency,
                        native_language=native_language,
                        learning_language=learning_language,
                    )
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("core-v2 practice task unavailable: %s", exc)
                    await websocket.send_json(
                        {"type": "error", "message": "Training task unavailable."}
                    )
                    continue

                active_tasks[task.task_id] = task
                generated_tasks += 1
                await websocket.send_json(
                    {
                        "type": "task",
                        "task_id": task.task_id,
                        "item_id": task.item_id,
                        "word": task.word,
                        "context": task.context,
                        "task_type": task.kind,
                        "question": task.question,
                        "reverse_text": task.reverse_text,
                        "counter": task.review_count,
                        "skill": task.skill,
                    }
                )

            elif message_type == "mark_known":
                item_id = str(message.get("item_id", ""))
                if repository.mark_known(item_id):
                    used_items.add(item_id)
                    active_tasks = {
                        task_id: task
                        for task_id, task in active_tasks.items()
                        if task.item_id != item_id
                    }

            elif message_type == "answer":
                task_id = str(message.get("task_id", ""))
                task = active_tasks.get(task_id)
                if task is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Training task expired."}
                    )
                    continue

                try:
                    evaluation = await answer_checker.execute(
                        AnswerCheckRequest(
                            task=task,
                            answer=str(message.get("answer", "")),
                            proficiency=proficiency,
                            native_language=native_language,
                            learning_language=learning_language,
                        )
                    )
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("core-v2 answer check unavailable: %s", exc)
                    await websocket.send_json(
                        {"type": "error", "message": "Answer check unavailable."}
                    )
                    continue

                if evaluation.should_update_schedule:
                    repository.apply_evaluation(task.item_id, evaluation, task.kind)
                    active_tasks.pop(task_id, None)
                await websocket.send_json(
                    {
                        "type": "result",
                        "task_id": task_id,
                        "outcome": evaluation.outcome,
                        "feedback": evaluation.feedback,
                    }
                )

    except WebSocketDisconnect:
        log.info("core-v2 training disconnected for user %r", username)
    except Exception:
        log.exception("core-v2 training socket failed for user %r", username)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
