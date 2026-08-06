"""Adaptive Practice Planner HTTP and WebSocket adapters.

WebSocket protocol (`/api/training/ws`). The client sends:

    {"type": "auth", "token": ...}        first message, always
    {"type": "init", "audio": bool,       audio = the client can speak, which
             "exclude": [item_id, ...]}   is what makes listening plannable
    {"type": "request_task"}              one at a time — see below
    {"type": "answer", "task_id": ..., "answer": ...,
             "response_seconds": float, "hints_used": int}
    {"type": "commit", "task_id": ..., "rating": "again"|"hard"|"good"|"easy"}
    {"type": "mark_known", "item_id": ...}

and receives `session`, `task`, `result`, `committed`, `done`, or `error`.

Two properties of this protocol are deliberate. Tasks are not pipelined: the
planner chooses each exercise from the answers that came before it, so a
prefetched task would have been planned against stale state. And grading is
split — `answer` returns a verdict plus a suggested FSRS rating, `commit`
applies it — so the learner can override the suggestion before anything is
scheduled.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import db
from auth import CurrentUser, ws_current_user
from config import REVIEW_WINDOW_HOURS
from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.practice import (
    AnswerCheckRequest,
    AnswerEvaluation,
    GradedAnswer,
    LearnerCapabilities,
    PracticePlan,
    PracticeQueue,
    PracticeSession,
    PracticeTask,
    SessionSummary,
    aggregate_skills,
    suggest_rating,
)
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.practice import LexiconPracticeRepository
from learning_core_v2_adapters.runtime import build_practice_planner, build_practice_services
from storage import get_storage


log = logging.getLogger(__name__)
router = APIRouter()
MAX_SESSION_TASKS = 10

# A drafted task can be unusable for reasons the planner cannot see in advance
# (a model that returns options without the expected answer, say). Re-plan a
# couple of times before telling the learner the session is broken.
_MAX_PLAN_ATTEMPTS = 3


class SkillProgress(BaseModel):
    skill: str
    confidence: float
    attempts: int


class TrainingInitResponse(BaseModel):
    available_words: int
    skills: list[SkillProgress]


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


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


def _studied(
    items: Sequence[LexicalItem], learning_language: str
) -> list[LexicalItem]:
    """Everything being learned in this language — due or not."""
    language = _language_base(learning_language)
    return [
        item
        for item in items
        if item.status == "learning" and _language_base(item.language) == language
    ]


@router.get("/api/training/init", response_model=TrainingInitResponse)
async def training_init(username: CurrentUser) -> TrainingInitResponse:
    storage = get_storage(username)
    repository = LexiconPracticeRepository(storage.lexicon, storage.save)
    learning_language = storage.settings.target_lang
    available = _queue().available(
        repository.items(),
        learning_language=learning_language,
        now=time.time(),
    )
    # Skill progress covers everything being learned, not only what is due —
    # the row should not swing every time a review window opens or closes.
    return TrainingInitResponse(
        available_words=len(available),
        skills=[
            SkillProgress(
                skill=report.skill,
                confidence=report.confidence,
                attempts=report.attempts,
            )
            for report in aggregate_skills(
                _studied(repository.items(), learning_language)
            )
        ],
    )


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


def _task_message(task: PracticeTask, plan: PracticePlan) -> dict[str, Any]:
    """Wire form of one task.

    The target word is deliberately absent: for recall, cloze and listening
    formats it *is* the answer, and the client has no use for it.
    """
    return {
        "type": "task",
        "task_id": task.task_id,
        "item_id": task.item_id,
        "task_kind": task.kind,
        "skill": task.skill,
        "stage": task.stage,
        "question": task.question,
        "options": list(task.options),
        "audio_text": task.audio_text,
        "hint": task.hint,
        "counter": task.review_count,
        "reason": {"code": task.reason.code, "skill": task.reason.skill},
        "is_correction": plan.stage != "core",
    }


def _summary_message(summary: SessionSummary) -> dict[str, Any]:
    return {
        "type": "done",
        "summary": {
            "reviewed": summary.reviewed,
            "corrections": summary.corrections,
            "skills": [
                {"skill": skill, "count": count} for skill, count in summary.skills
            ],
            "items": [
                {
                    "item_id": report.item_id,
                    "term": report.term,
                    "consolidated": report.consolidated,
                    "limiting_skill": report.limiting_skill,
                    "limiting_confidence": report.limiting_confidence,
                }
                for report in summary.items
            ],
        },
    }


def _committed_message(
    graded: GradedAnswer,
    session: PracticeSession,
    studied: Sequence[LexicalItem],
) -> dict[str, Any]:
    return {
        "type": "committed",
        "task_id": graded.task.task_id,
        "rating": graded.rating,
        "counts_as_review": graded.counts_as_review,
        "correction": (
            {"stage": graded.correction.stage, "skill": graded.correction.skill}
            if graded.correction
            else None
        ),
        # The progress row means the same thing all session long: confidence
        # per skill across everything being learned, refreshed after the answer
        # that just moved it. Per-sense profiles belong to the closing summary.
        "skills": [
            {
                "skill": report.skill,
                "confidence": report.confidence,
                "attempts": report.attempts,
            }
            for report in aggregate_skills(studied)
        ],
        "progress": {"done": session.reviewed, "target": session.target},
    }


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

    session = PracticeSession(
        build_practice_planner(queue),
        target_tasks=MAX_SESSION_TASKS,
        capabilities=LearnerCapabilities(),
        learning_language=learning_language,
    )
    # Answers are graded when the learner commits, so the suggested rating can
    # be overridden before anything reaches FSRS.
    pending: dict[str, tuple[AnswerEvaluation, float, int]] = {}

    async def send_next_task() -> None:
        for _ in range(_MAX_PLAN_ATTEMPTS):
            plan = session.plan_next(repository.items(), now=time.time())
            if plan is None:
                await websocket.send_json(_summary_message(session.summary()))
                return
            try:
                task = await task_builder.execute(
                    plan,
                    proficiency=proficiency,
                    native_language=native_language,
                    learning_language=learning_language,
                )
            except ValueError as exc:
                log.warning("planner produced an unusable %s task: %s", plan.kind, exc)
                # Retire the sense for this session, otherwise the next attempt
                # re-plans the same one and burns the whole retry budget on it.
                session.exclude([plan.item.item_id])
                continue
            except LanguageProviderError as exc:
                log.warning("core-v2 practice task unavailable: %s", exc)
                await websocket.send_json(
                    {"type": "error", "message": "Training task unavailable."}
                )
                return
            session.register(plan, task)
            await websocket.send_json(_task_message(task, plan))
            return
        await websocket.send_json(
            {"type": "error", "message": "Training task unavailable."}
        )

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
                # Listening tasks are voiced by the client, so the client is the
                # only place that knows whether they can be presented at all.
                session = PracticeSession(
                    build_practice_planner(queue),
                    target_tasks=MAX_SESSION_TASKS,
                    capabilities=LearnerCapabilities(
                        audio=bool(message.get("audio", False))
                    ),
                    learning_language=learning_language,
                )
                pending.clear()
                session.exclude(str(value) for value in message.get("exclude", []))
                available = queue.available(
                    repository.items(),
                    learning_language=learning_language,
                    now=time.time(),
                )
                await websocket.send_json(
                    {
                        "type": "session",
                        "target": min(len(available), MAX_SESSION_TASKS),
                        "audio": session.capabilities.audio,
                    }
                )

            elif message_type == "request_task":
                await send_next_task()

            elif message_type == "mark_known":
                item_id = str(message.get("item_id", ""))
                if repository.mark_known(item_id):
                    session.drop_item(item_id)

            elif message_type == "answer":
                task_id = str(message.get("task_id", ""))
                task = session.task(task_id)
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

                response_seconds = max(0.0, float(message.get("response_seconds", 0) or 0))
                hints_used = max(0, int(message.get("hints_used", 0) or 0))
                suggested = suggest_rating(
                    task.kind,
                    evaluation.outcome,
                    response_seconds=response_seconds,
                    hints_used=hints_used,
                    corrected=task.stage != "core",
                )
                if suggested is not None:
                    pending[task_id] = (evaluation, response_seconds, hints_used)

                await websocket.send_json(
                    {
                        "type": "result",
                        "task_id": task_id,
                        "outcome": evaluation.outcome,
                        "feedback": evaluation.feedback,
                        "error_note": evaluation.error_note,
                        "suggested_rating": suggested,
                        # The learner has already answered; showing the target
                        # now is the first step of the corrective chain.
                        "expected_answer": (
                            task.expected_answer if evaluation.outcome != "correct" else ""
                        ),
                    }
                )

            elif message_type == "commit":
                task_id = str(message.get("task_id", ""))
                task = session.task(task_id)
                held = pending.pop(task_id, None)
                if task is None or held is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Training task expired."}
                    )
                    continue
                evaluation, response_seconds, hints_used = held
                requested = message.get("rating")
                graded = session.grade(
                    task,
                    evaluation,
                    now=time.time(),
                    response_seconds=response_seconds,
                    hints_used=hints_used,
                    requested_rating=str(requested) if requested else None,
                )
                repository.apply_grade(graded)
                await websocket.send_json(
                    _committed_message(
                        graded, session, _studied(repository.items(), learning_language)
                    )
                )

    except WebSocketDisconnect:
        log.info("core-v2 training disconnected for user %r", username)
    except Exception:
        log.exception("core-v2 training socket failed for user %r", username)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
