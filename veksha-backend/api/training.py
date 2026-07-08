"""
api/training.py — WebSocket training session endpoints.

  GET  /api/training/init       — number of words available right now
  POST /api/training/validate   — check which words still exist in KB
  GET  /api/training/review_log — latest reviews (FSRS log), newest first
  WS   /api/training/ws         — word training session

WebSocket protocol (client → server):
  {"type": "auth", "token": "..."}   — must be the first message (see auth.py)
  {"type": "init", "exclude": ["word1", ...]}
  {"type": "request_task"}
  {"type": "answer", "task_id": "...", "word": "...", "question": "...", "answer": "..."}

WebSocket protocol (server → client):
  {"type": "task", "task_id": "...", "word": "...", "context": "...",
   "task_type": "...", "question": "...", "reverse_text": ""}
  {"type": "result", "task_id": "...", "outcome": "...", "feedback": "..."}
  {"type": "done"}
  {"type": "error", "message": "..."}
"""
from __future__ import annotations

import json
import logging
import random

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import db
import training as training_mod
from auth import CurrentUser, ws_current_user
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class TrainingInitResponse(BaseModel):
    available_words: int


class TrainingValidateRequest(BaseModel):
    word_names: list[str]


class TrainingValidateResponse(BaseModel):
    valid: list[str]


@router.get("/api/training/init", response_model=TrainingInitResponse)
async def training_init(username: CurrentUser) -> TrainingInitResponse:
    storage = get_storage(username)
    available = training_mod.get_available_words(storage)
    return TrainingInitResponse(available_words=len(available))


@router.post("/api/training/validate", response_model=TrainingValidateResponse)
async def training_validate(req: TrainingValidateRequest, username: CurrentUser) -> TrainingValidateResponse:
    storage = get_storage(username)
    valid = [name for name in req.word_names if storage.find_word(name) is not None]
    return TrainingValidateResponse(valid=valid)


class ReviewLogEntry(BaseModel):
    word: str
    ts: float
    rating: int              # 1 Again / 2 Hard / 3 Good / 4 Easy
    outcome: str             # raw checker outcome ("correct" / "vague" / "incorrect")
    task_type: str
    elapsed_days: float
    scheduled_days: float
    stability: float
    difficulty: float
    retrievability: Optional[float]  # predicted recall before the review; None on first review


class ReviewLogResponse(BaseModel):
    reviews: list[ReviewLogEntry]


@router.get("/api/training/review_log", response_model=ReviewLogResponse)
async def training_review_log(
    username: CurrentUser, word: Optional[str] = None, limit: int = 50,
) -> ReviewLogResponse:
    rows = db.review_log_recent(username, word=word, limit=limit)
    return ReviewLogResponse(reviews=[ReviewLogEntry(**row) for row in rows])


@router.websocket("/api/training/ws")
async def training_ws(websocket: WebSocket) -> None:
    username = await ws_current_user(websocket)
    if username is None:
        return  # socket already closed with 4401
    storage = get_storage(username)
    level = storage.settings.english_level or "intermediate"
    native_lang = storage.settings.native_lang or "en"
    used_words: set[str] = set()
    task_types: dict[str, str] = {}  # task_id -> task_type, for the review log

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "init":
                used_words.update(msg.get("exclude", []))

            elif msg_type == "request_task":
                available = training_mod.get_available_words(storage)
                remaining = [w for w in available if w.name not in used_words]
                if not remaining:
                    await websocket.send_json({"type": "done"})
                    continue
                word = random.choice(remaining)
                used_words.add(word.name)
                task = await training_mod.generate_task(word, level, native_lang=native_lang)
                task_types[task["task_id"]] = task["task_type"]
                await websocket.send_json({"type": "task", **task})

            elif msg_type == "mark_known":
                word_name = msg.get("word", "")
                word_obj = storage.find_word(word_name)
                if word_obj:
                    word_obj.known = True
                    storage.save()
                    log.info("[training_ws] mark_known: word=%r user=%r", word_name, username)

            elif msg_type == "answer":
                result = await training_mod.check_answer(
                    word=msg.get("word", ""),
                    question=msg.get("question", ""),
                    answer=msg.get("answer", ""),
                    level=level,
                    native_lang=native_lang,
                )
                if result["update_kb"]:
                    word_obj = storage.find_word(msg.get("word", ""))
                    if word_obj:
                        storage.apply_review_result(
                            word_obj, result["outcome"],
                            task_type=task_types.get(msg.get("task_id", ""), ""),
                        )
                        storage.save()
                await websocket.send_json({
                    "type": "result",
                    "task_id": msg.get("task_id"),
                    "outcome": result["outcome"],
                    "feedback": result["feedback"],
                })

    except WebSocketDisconnect:
        log.info("[training_ws] disconnected: user=%r", username)
    except Exception:
        log.exception("[training_ws] error for user %r", username)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
