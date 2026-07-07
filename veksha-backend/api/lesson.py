"""
api/lesson.py — topic lesson endpoints.

  GET  /api/lesson-topics — list topics for the current user
  POST /api/lesson-topics — create a new topic
  WS   /api/lesson/ws     — topic learning session

WebSocket protocol (client → server):
  {"type": "init", "topic_name": "..."}
  {"type": "request_question"}
  {"type": "answer", "question_id": "...", "block_name": "...",
   "question": "...", "answer": "..."}

WebSocket protocol (server → client):
  {"type": "ready", "blocks": [...], "total_questions": N}
  {"type": "question", "question_id": "...", "block_name": "...", "question": "..."}
  {"type": "result", "question_id": "...", "outcome": "...", "feedback": "..."}
  {"type": "done"}
  {"type": "error", "message": "..."}
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import i18n
import lesson as lesson_mod
from auth import CurrentUser, ws_current_user
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class LessonTopicSummary(BaseModel):
    name: str
    block_count: int
    mastery: float
    last_reviewed: float | None = None


class LessonTopicsResponse(BaseModel):
    topics: list[LessonTopicSummary]


class CreateLessonTopicRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@router.get("/api/lesson-topics", response_model=LessonTopicsResponse)
async def api_get_lesson_topics(username: CurrentUser) -> LessonTopicsResponse:
    storage = get_storage(username)
    topics = lesson_mod.list_topics(storage)
    return LessonTopicsResponse(topics=[LessonTopicSummary(**t) for t in topics])


@router.post("/api/lesson-topics", response_model=LessonTopicSummary)
async def api_create_lesson_topic(req: CreateLessonTopicRequest, username: CurrentUser) -> LessonTopicSummary:
    storage = get_storage(username)
    topic = lesson_mod.create_topic(storage, req.name)
    return LessonTopicSummary(
        name=topic.name,
        block_count=len([b for b in topic.blocks if b.content_json]),
        mastery=round(topic.avg_mastery(), 2),
        last_reviewed=topic.last_reviewed,
    )


@router.websocket("/api/lesson/ws")
async def lesson_ws(websocket: WebSocket) -> None:
    username = await ws_current_user(websocket)
    if username is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    storage = get_storage(username)
    level = storage.settings.english_level or "intermediate"
    native_lang = storage.settings.native_lang or "en"
    target_lang = storage.settings.target_lang or "en"
    goals = storage.settings.goals or ""

    topic = None
    question_plan: list[str] = []
    plan_index = 0
    session_history: dict[str, list[str]] = {}
    results_by_block: dict[str, list[str]] = {}
    qa_by_block: dict[str, list[tuple[str, str]]] = {}
    active_questions: dict[str, tuple[str, str]] = {}

    async def _finish_session() -> None:
        if topic and (results_by_block or qa_by_block):
            lesson_mod.apply_session_results(topic, results_by_block, qa_by_block)
            storage.save()
            log.info("[lesson_ws] session saved for topic %r user %r", topic.name, username)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "init":
                topic_name = msg.get("topic_name", "")
                topic = storage.find_lesson_topic(topic_name)
                if not topic:
                    topic = lesson_mod.create_topic(storage, topic_name)

                blocks = await lesson_mod.select_session_blocks(
                    topic, level, goals=goals,
                    native_lang=native_lang, target_lang=target_lang, storage=storage,
                )
                storage.save()

                if not blocks:
                    await websocket.send_json({"type": "error", "message": i18n.get_string("lesson_no_blocks", native_lang)})
                    continue

                question_plan = lesson_mod.make_question_plan(blocks)
                plan_index = 0
                session_history = {b.name: [] for b in blocks}
                results_by_block = {b.name: [] for b in blocks}
                qa_by_block = {b.name: [] for b in blocks}

                blocks_data = [{"name": b.name, "content": json.loads(b.content_json)} for b in blocks]
                await websocket.send_json({
                    "type": "ready",
                    "blocks": blocks_data,
                    "total_questions": lesson_mod.QUESTIONS_PER_SESSION,
                })

            elif msg_type == "request_question":
                if topic is None or plan_index >= len(question_plan):
                    await websocket.send_json({"type": "done"})
                    continue

                block_name = question_plan[plan_index]
                plan_index += 1
                block = topic.find_block(block_name)
                if not block:
                    await websocket.send_json({"type": "done"})
                    continue

                q = await lesson_mod.generate_question(
                    topic=topic, block=block,
                    session_history=session_history.get(block_name, []),
                    level=level, native_lang=native_lang, target_lang=target_lang,
                )
                session_history.setdefault(block_name, []).append(q["question"])
                active_questions[q["question_id"]] = (block_name, q["question"])
                await websocket.send_json({"type": "question", **q})

            elif msg_type == "answer":
                if topic is None:
                    continue
                question_id = msg.get("question_id", "")
                block_name = msg.get("block_name", "")
                question_text = msg.get("question", "")
                answer_text = msg.get("answer", "")

                if question_id in active_questions:
                    block_name, question_text = active_questions.pop(question_id)

                result = await lesson_mod.check_answer(
                    topic_name=topic.name, block_name=block_name,
                    question=question_text, answer=answer_text,
                    level=level, native_lang=native_lang, target_lang=target_lang,
                )
                if result["update_kb"]:
                    results_by_block.setdefault(block_name, []).append(result["outcome"])
                    qa_by_block.setdefault(block_name, []).append((question_text, result["outcome"]))

                total_answered = sum(len(v) for v in results_by_block.values())
                await websocket.send_json({
                    "type": "result",
                    "question_id": msg.get("question_id"),
                    "outcome": result["outcome"],
                    "feedback": result["feedback"],
                })
                if total_answered >= lesson_mod.QUESTIONS_PER_SESSION and plan_index >= len(question_plan):
                    await _finish_session()
                    await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        log.info("[lesson_ws] disconnected: user=%r topic=%r", username, topic.name if topic else None)
        await _finish_session()
    except Exception:
        log.exception("[lesson_ws] error for user %r", username)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
        await _finish_session()
