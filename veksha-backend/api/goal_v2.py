"""HTTP and WebSocket adapters for goal-oriented lessons.

The socket runs one goal at a time. It never holds a precomputed sequence of
steps: after every answer the domain re-plans, so the next question depends on
the last one. Steps live server-side keyed by ``step_id`` — the criterion and
activity a client echoes back are ignored when the answer is judged.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import i18n
from auth import CurrentUser, ws_current_user
from learning_core_v2.acquisition import SuggestVocabulary, VocabularyProposal
from learning_core_v2.goal import (
    DEFAULT_MINUTES,
    CriterionProgress,
    GoalMaterial,
    GoalReport,
    GoalStep,
    LearnerProfile,
    LearningGoal,
    RecordEvidence,
    goal_achieved,
    goal_progress,
    state_goal,
    time_exhausted,
)
from learning_core_v2.grammar_memory import GrammarObservation, RememberGrammar
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import build_goal_services
from repositories.goals import material_to_dict
from storage import UserStorage, get_storage, learner_profile
from writing_systems import writing_system_profile


log = logging.getLogger(__name__)
router = APIRouter()

MAX_MATERIAL_CHARS = 20000
MIN_MINUTES = 3
MAX_MINUTES = 60


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class CriterionView(BaseModel):
    criterion_id: str
    statement: str
    depth: int
    status: str
    attempts: int
    cause: str | None = None


class GoalSummary(BaseModel):
    goal_id: str
    statement: str
    framed: bool
    achieved: bool
    progress: float
    minutes: int
    spent_seconds: float
    has_material: bool
    criteria: list[CriterionView]
    last_worked_at: float | None = None
    kind: Literal["standard", "alphabet"] = "standard"


class GoalListResponse(BaseModel):
    goals: list[GoalSummary]


class CreateGoalRequest(BaseModel):
    statement: str = Field(..., min_length=1, max_length=200)
    material: str = Field("", max_length=MAX_MATERIAL_CHARS)
    material_url: str = Field("", max_length=2000)
    minutes: int = Field(DEFAULT_MINUTES, ge=MIN_MINUTES, le=MAX_MINUTES)
    kind: Literal["standard", "alphabet"] = "standard"


def _criterion_views(goal: LearningGoal) -> list[CriterionView]:
    return [
        CriterionView(
            criterion_id=item.criterion.criterion_id,
            statement=item.criterion.statement,
            depth=item.criterion.depth,
            status=item.status,
            attempts=item.attempts,
            cause=item.cause,
        )
        for item in goal_progress(goal)
    ]


def _share_settled(goal: LearningGoal) -> float:
    """How much of the goal is behind the learner, by settled criteria."""
    progress = goal_progress(goal)
    if not progress:
        return 0.0
    return round(sum(1 for item in progress if item.settled) / len(progress), 2)


def _summary(goal: LearningGoal) -> GoalSummary:
    return GoalSummary(
        goal_id=goal.goal_id,
        statement=goal.statement,
        framed=goal.framed,
        achieved=goal_achieved(goal),
        progress=_share_settled(goal),
        minutes=goal.profile.minutes,
        spent_seconds=round(goal.spent_seconds, 1),
        has_material=goal.material.present,
        criteria=_criterion_views(goal),
        last_worked_at=goal.last_worked_at,
        kind=goal.kind,
    )


def _set_literacy_stage(storage: UserStorage, stage: str) -> None:
    language = storage.settings.target_lang
    if not language:
        return
    current = storage.settings.language_settings.get(language, {})
    storage.settings.language_settings[language] = {
        "level": current.get("level", ""),
        "goals": current.get("goals", ""),
        "prompt": current.get("prompt", ""),
        "literacy_stage": stage,
    }


@router.get("/api/learning-goals", response_model=GoalListResponse)
async def api_list_goals(username: CurrentUser) -> GoalListResponse:
    storage = get_storage(username)
    goals = storage.goals.for_language(storage.settings.target_lang or "en")
    return GoalListResponse(goals=[_summary(goal) for goal in goals])


@router.post("/api/learning-goals", response_model=GoalSummary)
async def api_create_goal(req: CreateGoalRequest, username: CurrentUser) -> GoalSummary:
    """State a goal. Framing it into criteria happens when the session opens."""
    storage = get_storage(username)
    if req.kind == "alphabet":
        writing = writing_system_profile(
            storage.settings.native_lang,
            storage.settings.target_lang,
            storage.settings.english_level,
            storage.settings.literacy_stage,
        )
        if not writing.course_available:
            raise HTTPException(
                status_code=422,
                detail="An alphabet course is not available for this language pair.",
            )
    profile = _profile(storage, minutes=req.minutes)
    try:
        goal = state_goal(
            req.statement,
            profile,
            material=_material(req.material, req.material_url),
            created_at=time.time(),
            kind=req.kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = storage.goals.find(goal.goal_id)
    if existing is None:
        if goal.kind == "alphabet":
            _set_literacy_stage(storage, "learning")
        storage.goals.put(goal)
        storage.save()
        return _summary(goal)
    return _summary(existing)


@router.delete("/api/learning-goals/{goal_id}")
async def api_delete_goal(goal_id: str, username: CurrentUser) -> dict:
    storage = get_storage(username)
    if not storage.goals.remove(goal_id):
        raise HTTPException(status_code=404, detail="Learning goal not found.")
    storage.save()
    return {"ok": True}


def _profile(storage: UserStorage, *, minutes: int = DEFAULT_MINUTES) -> LearnerProfile:
    base = learner_profile(storage.settings)
    return LearnerProfile(
        proficiency=base.proficiency,
        native_language=base.native_language,
        learning_language=base.learning_language,
        minutes=max(MIN_MINUTES, min(MAX_MINUTES, minutes)),
        writing_support=base.writing_support,
        script_name=base.script_name,
        transcription_mode=base.transcription_mode,
    )


def _material(text: str, source_url: str) -> GoalMaterial:
    return GoalMaterial(text=text[:MAX_MATERIAL_CHARS], source_url=source_url[:2000])


# ---------------------------------------------------------------------------
# WebSocket session
# ---------------------------------------------------------------------------


def _step_payload(goal: LearningGoal, step: GoalStep) -> dict:
    criterion = goal.criterion(step.criterion_id)
    return {
        "type": "step",
        "step_id": step.step_id,
        "criterion_id": step.criterion_id,
        "criterion": criterion.statement if criterion else "",
        "activity": step.activity,
        "reason": step.reason,
        "material": material_to_dict(step.material),
        "question": step.question,
    }


def _progress_payload(goal: LearningGoal) -> list[dict]:
    return [item.model_dump() for item in _criterion_views(goal)]


def _criterion_report(items: tuple[CriterionProgress, ...]) -> list[dict]:
    return [
        {
            "criterion_id": item.criterion.criterion_id,
            "statement": item.criterion.statement,
            "status": item.status,
            "attempts": item.attempts,
            "cause": item.cause,
        }
        for item in items
    ]


def _report_payload(report: GoalReport) -> dict:
    return {
        "type": "summary",
        "achieved": report.achieved,
        "stopped_on_time": report.stopped_on_time,
        "narrative": report.narrative,
        "next_goal": report.next_goal,
        "proven": _criterion_report(report.proven),
        "shaky": _criterion_report(report.shaky),
        "examples": list(report.examples),
        "terms": [
            {"term": item.term, "translation": item.translation}
            for item in report.terms
        ],
        "patterns": [
            {"label": item.label, "category": item.category, "example": item.example}
            for item in report.patterns
        ],
    }


def _harvest(storage: UserStorage, goal: LearningGoal) -> None:
    """Send what the lesson turned up to the inbox and to Pattern Workshop.

    A goal-oriented lesson surfaces words and constructions the learner has not
    formally met. They arrive as suggestions, never as decided knowledge — the
    same rule the rest of Veksha follows for anything the learner did not ask
    for by name.
    """
    changed = False
    language = goal.profile.learning_language
    observed_at = time.time()

    suggest = SuggestVocabulary()
    items = storage.lexicon.all()
    for term in goal.terms:
        try:
            items = suggest.execute(
                items,
                VocabularyProposal(
                    term=term.term,
                    language=language,
                    translation=term.translation,
                    context=term.context,
                    source_url=goal.material.source_url,
                ),
                observed_at=observed_at,
            )
        except ValueError:
            continue
    if items != storage.lexicon.all():
        storage.lexicon.replace_all(items)
        changed = True

    remember = RememberGrammar()
    memory = list(storage.grammar.all())
    for pattern in goal.patterns:
        try:
            memory = list(
                remember.execute(
                    memory,
                    GrammarObservation(
                        language=language,
                        category=pattern.category,
                        label=pattern.label,
                        explanation=pattern.explanation,
                        example=pattern.example,
                        source_url=goal.material.source_url,
                    ),
                    item_id=str(uuid.uuid4()),
                    observed_at=observed_at,
                )
            )
        except ValueError:
            continue
    if memory != list(storage.grammar.all()):
        storage.grammar.replace_all(memory)
        changed = True

    if changed:
        storage.save()


@router.websocket("/api/learning-goals/ws")
async def goal_ws(websocket: WebSocket) -> None:
    username = await ws_current_user(websocket)
    if username is None:
        return

    storage = get_storage(username)
    services = build_goal_services()
    recorder = RecordEvidence(services.route)

    goal: LearningGoal | None = None
    open_steps: dict[str, GoalStep] = {}
    asked: list[str] = []
    step_started_at = 0.0
    closed = False

    def persist() -> None:
        if goal is not None:
            storage.goals.put(goal)
            storage.save()

    async def fail(message: str) -> None:
        await websocket.send_json({"type": "error", "message": message})

    async def send_summary() -> None:
        nonlocal closed
        if goal is None or closed:
            return
        closed = True
        _harvest(storage, goal)
        if goal_achieved(goal) and goal.kind == "alphabet":
            _set_literacy_stage(storage, "mastered")
            storage.save()
        try:
            report = await services.closer.execute(goal)
        except (LanguageProviderError, ValueError) as exc:
            log.warning("goal summary unavailable: %s", exc)
            await websocket.send_json(
                {
                    "type": "summary",
                    "achieved": goal_achieved(goal),
                    "stopped_on_time": time_exhausted(goal),
                    "narrative": "",
                    "next_goal": "",
                    "proven": _criterion_report(
                        tuple(item for item in goal_progress(goal) if item.settled)
                    ),
                    "shaky": _criterion_report(
                        tuple(item for item in goal_progress(goal) if not item.settled)
                    ),
                    "examples": [],
                    "terms": [],
                    "patterns": [],
                }
            )
            return
        await websocket.send_json(_report_payload(report))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await fail("Invalid message.")
                continue
            if not isinstance(message, dict):
                await fail("Invalid message.")
                continue

            message_type = message.get("type")

            if message_type == "ping":
                # Application-level traffic prevents idle proxy timeouts while
                # the learner is reading a lesson step. A response also lets
                # intermediaries see traffic in both directions.
                await websocket.send_json({"type": "pong"})

            elif message_type == "init":
                profile = _profile(
                    storage, minutes=_minutes(message.get("minutes"))
                )
                goal = _resolve_goal(storage, message, profile)
                if goal is None:
                    await fail(
                        i18n.get_string("goal_missing", profile.native_language)
                    )
                    continue

                if not goal.framed:
                    try:
                        goal = await services.framer.execute(goal)
                    except (LanguageProviderError, ValueError) as exc:
                        log.warning("goal framing unavailable: %s", exc)
                        await fail(
                            i18n.get_string(
                                "goal_no_criteria", profile.native_language
                            )
                        )
                        goal = None
                        continue

                resumed = bool(goal.evidence)
                storage.goals.put(goal)
                storage.save()
                open_steps = {}
                asked = []
                closed = False
                await websocket.send_json(
                    {
                        "type": "goal",
                        "goal_id": goal.goal_id,
                        "statement": goal.statement,
                        "minutes": goal.profile.minutes,
                        "spent_seconds": round(goal.spent_seconds, 1),
                        "has_material": goal.material.present,
                        "resumed": resumed,
                        "achieved": goal_achieved(goal),
                        "criteria": _progress_payload(goal),
                    }
                )

            elif message_type == "next_step":
                if goal is None:
                    await fail("Lesson is not initialized.")
                    continue
                if goal_achieved(goal) or time_exhausted(goal):
                    await send_summary()
                    continue
                plan = goal.next_plan or services.route.plan(goal)
                if plan is None:
                    await send_summary()
                    continue
                try:
                    step = await services.step_builder.execute(
                        goal, plan, previous_questions=asked[-6:]
                    )
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("goal step unavailable: %s", exc)
                    await fail("Next step unavailable.")
                    continue

                open_steps[step.step_id] = step
                asked.append(step.question)
                step_started_at = time.time()
                await websocket.send_json(_step_payload(goal, step))

            elif message_type == "answer":
                if goal is None:
                    await fail("Lesson is not initialized.")
                    continue
                step = open_steps.get(str(message.get("step_id", "")))
                if step is None:
                    await fail("Lesson step expired.")
                    continue
                try:
                    evaluation = await services.answer_checker.execute(
                        goal, step, str(message.get("answer", ""))
                    )
                except (LanguageProviderError, ValueError) as exc:
                    log.warning("goal answer check unavailable: %s", exc)
                    await fail("Answer check unavailable.")
                    continue

                if evaluation.should_record:
                    open_steps.pop(step.step_id, None)
                    goal = recorder.execute(
                        goal,
                        step,
                        evaluation,
                        observed_at=time.time(),
                        answer=str(message.get("answer", "")),
                        elapsed_seconds=max(0.0, time.time() - step_started_at),
                    )
                    persist()

                await websocket.send_json(
                    {
                        "type": "result",
                        "step_id": step.step_id,
                        "outcome": evaluation.outcome,
                        "cause": evaluation.cause,
                        "feedback": evaluation.feedback,
                        "achieved": goal_achieved(goal),
                        "spent_seconds": round(goal.spent_seconds, 1),
                        "criteria": _progress_payload(goal),
                    }
                )
                if goal_achieved(goal) or time_exhausted(goal):
                    await send_summary()

            elif message_type == "finish":
                if goal is None:
                    await fail("Lesson is not initialized.")
                    continue
                await send_summary()

    except WebSocketDisconnect:
        log.info("goal lesson disconnected for user %r", username)
        persist()
    except Exception:
        log.exception("goal lesson socket failed for user %r", username)
        try:
            await websocket.send_json(
                {"type": "error", "message": "Internal server error"}
            )
        except Exception:
            pass
        persist()


def _minutes(value: object) -> int:
    try:
        return max(MIN_MINUTES, min(MAX_MINUTES, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_MINUTES


def _resolve_goal(
    storage: UserStorage, message: dict, profile: LearnerProfile
) -> LearningGoal | None:
    """Find the goal this session is about, creating it if it is brand new."""
    goal_id = str(message.get("goal_id", "")).strip()
    if goal_id:
        return storage.goals.find(goal_id)

    statement = str(message.get("statement", ""))
    if not statement.strip():
        return None
    try:
        fresh = state_goal(
            statement,
            profile,
            material=_material(
                str(message.get("material", "")), str(message.get("material_url", ""))
            ),
            created_at=time.time(),
        )
    except ValueError:
        return None
    return storage.goals.find(fresh.goal_id) or fresh
