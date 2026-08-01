"""HTTP and WebSocket adapters for the independently rewritten lesson core."""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import i18n
from auth import CurrentUser, ws_current_user
from learning_core_v2.lesson import (
    AnswerRequest,
    LearnerProfile,
    LessonQuestion,
    LessonTopic,
    LessonUnit,
    QuestionSchedule,
    RecordedAnswer,
    RecordLessonResults,
    create_topic,
    summarize_topic,
)
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import build_lesson_services
from repositories.lessons import material_to_dict
from storage import get_storage


log = logging.getLogger(__name__)
router = APIRouter()
QUESTION_COUNT = 6


class LessonTopicSummary(BaseModel):
    name: str
    block_count: int
    mastery: float
    last_reviewed: float | None = None


class LessonTopicsResponse(BaseModel):
    topics: list[LessonTopicSummary]


class CreateLessonTopicRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


def _summary(topic: LessonTopic) -> LessonTopicSummary:
    value = summarize_topic(topic)
    return LessonTopicSummary(
        name=value.name,
        block_count=value.unit_count,
        mastery=value.mastery,
        last_reviewed=value.last_reviewed_at,
    )


@router.get("/api/lesson-topics", response_model=LessonTopicsResponse)
async def api_get_lesson_topics(username: CurrentUser) -> LessonTopicsResponse:
    repository = get_storage(username).lessons
    return LessonTopicsResponse(topics=[_summary(topic) for topic in repository.topics()])


@router.post("/api/lesson-topics", response_model=LessonTopicSummary)
async def api_create_lesson_topic(
    req: CreateLessonTopicRequest, username: CurrentUser
) -> LessonTopicSummary:
    storage = get_storage(username)
    repository = storage.lessons
    topic = repository.find(req.name)
    if topic is None:
        try:
            topic = create_topic(req.name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        repository.put(topic)
        storage.save()
    return _summary(topic)


def _profile(storage) -> LearnerProfile:
    return LearnerProfile(
        proficiency=storage.settings.english_level or "intermediate",
        native_language=storage.settings.native_lang or "en",
        learning_language=storage.settings.target_lang or "en",
        goals=storage.settings.goals or "",
    )


@router.websocket("/api/lesson/ws")
async def lesson_ws(websocket: WebSocket) -> None:
    username = await ws_current_user(websocket)
    if username is None:
        return

    storage = get_storage(username)
    repository = storage.lessons
    profile = _profile(storage)
    preparer, question_builder, answer_checker = build_lesson_services()
    schedule = QuestionSchedule(QUESTION_COUNT)
    recorder = RecordLessonResults()

    topic: LessonTopic | None = None
    session_units: dict[str, LessonUnit] = {}
    question_plan: tuple[str, ...] = ()
    plan_index = 0
    previous_questions: dict[str, list[str]] = {}
    active_questions: dict[str, tuple[LessonQuestion, LessonUnit]] = {}
    answers_by_unit: dict[str, list[RecordedAnswer]] = {}
    completed_answers = 0

    async def flush_results() -> None:
        nonlocal topic, answers_by_unit
        if topic is None or not answers_by_unit:
            return
        topic = recorder.execute(topic, answers_by_unit, reviewed_at=time.time())
        repository.put(topic)
        storage.save()
        answers_by_unit = {}

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid message."})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "message": "Invalid message."})
                continue

            message_type = message.get("type")
            if message_type == "init":
                await flush_results()
                name = str(message.get("topic_name", ""))
                try:
                    topic = repository.find(name) or create_topic(name)
                except ValueError:
                    await websocket.send_json(
                        {"type": "error", "message": "Lesson topic is required."}
                    )
                    continue
                try:
                    prepared = await preparer.execute(topic, profile)
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("core-v2 lesson preparation unavailable: %s", exc)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": i18n.get_string(
                                "lesson_no_blocks", profile.native_language
                            ),
                        }
                    )
                    continue

                topic = prepared.topic
                repository.put(topic)
                storage.save()
                session_units = {unit.name: unit for unit in prepared.units}
                question_plan = schedule.arrange(prepared.units)
                plan_index = 0
                previous_questions = {unit.name: [] for unit in prepared.units}
                active_questions = {}
                answers_by_unit = {}
                completed_answers = 0
                await websocket.send_json(
                    {
                        "type": "ready",
                        "blocks": [
                            {
                                "name": unit.name,
                                "content": material_to_dict(unit.material),
                            }
                            for unit in prepared.units
                            if unit.material is not None
                        ],
                        "total_questions": len(question_plan),
                    }
                )

            elif message_type == "request_question":
                if topic is None or plan_index >= len(question_plan):
                    await websocket.send_json({"type": "done"})
                    continue
                unit_name = question_plan[plan_index]
                unit = session_units.get(unit_name)
                if unit is None:
                    await websocket.send_json({"type": "done"})
                    continue
                try:
                    question = await question_builder.execute(
                        topic=topic.name,
                        unit=unit,
                        previous_questions=previous_questions.get(unit_name, ()),
                        profile=profile,
                    )
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("core-v2 lesson question unavailable: %s", exc)
                    await websocket.send_json(
                        {"type": "error", "message": "Lesson question unavailable."}
                    )
                    continue

                plan_index += 1
                previous_questions.setdefault(unit_name, []).append(question.text)
                active_questions[question.question_id] = (question, unit)
                await websocket.send_json(
                    {
                        "type": "question",
                        "question_id": question.question_id,
                        "block_name": question.unit_name,
                        "question": question.text,
                    }
                )

            elif message_type == "answer":
                if topic is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Lesson is not initialized."}
                    )
                    continue
                question_id = str(message.get("question_id", ""))
                active = active_questions.get(question_id)
                if active is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Lesson question expired."}
                    )
                    continue
                question, unit = active
                try:
                    result = await answer_checker.execute(
                        AnswerRequest(
                            topic=topic.name,
                            unit=unit,
                            question=question.text,
                            answer=str(message.get("answer", "")),
                            profile=profile,
                        )
                    )
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("core-v2 lesson answer check unavailable: %s", exc)
                    await websocket.send_json(
                        {"type": "error", "message": "Answer check unavailable."}
                    )
                    continue

                if result.should_record:
                    active_questions.pop(question_id, None)
                    answers_by_unit.setdefault(unit.name, []).append(
                        RecordedAnswer(question.text, result.outcome)
                    )
                    completed_answers += 1
                await websocket.send_json(
                    {
                        "type": "result",
                        "question_id": question_id,
                        "outcome": result.outcome,
                        "feedback": result.feedback,
                    }
                )
                if completed_answers >= len(question_plan) and question_plan:
                    await flush_results()
                    await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        log.info("core-v2 lesson disconnected for user %r", username)
        await flush_results()
    except Exception:
        log.exception("core-v2 lesson socket failed for user %r", username)
        try:
            await websocket.send_json(
                {"type": "error", "message": "Internal server error"}
            )
        except Exception:
            pass
        await flush_results()
