"""Repository and persistence mapping for goal-oriented lessons.

A goal outlives the session that started it: the criteria, the evidence behind
each one, and the plan for the next step are all written back, so reopening a
goal tomorrow resumes the route instead of restarting it.
"""

from __future__ import annotations

from collections.abc import Iterable

from learning_core_v2.goal import (
    ACTIVITY_DEMAND,
    CAUSES,
    MAX_DEPTH,
    MIN_DEPTH,
    DiscoveredPattern,
    DiscoveredTerm,
    Evidence,
    GoalMaterial,
    LearnerProfile,
    LearningGoal,
    RoutePlan,
    SuccessCriterion,
    goal_id_for,
)


_OUTCOMES = {"correct", "vague", "incorrect", "garbage"}
_REASONS = {
    "diagnose",
    "nearest_gap",
    "repair_cause",
    "raise_demand",
    "consolidate",
    "final_check",
}


class GoalRepository:
    def __init__(self, goals: Iterable[LearningGoal] = ()) -> None:
        self._goals = list(goals)

    @classmethod
    def from_document(cls, values: object, profile: LearnerProfile) -> "GoalRepository":
        if not isinstance(values, list):
            return cls()
        return cls(
            _goal_from_dict(value, profile)
            for value in values
            if isinstance(value, dict) and str(value.get("statement", "")).strip()
        )

    @classmethod
    def from_legacy_topics(
        cls, values: object, profile: LearnerProfile
    ) -> "GoalRepository":
        """Carry pre-goal lesson topics over as goals of a general kind.

        A topic recorded only a name and per-block scores; neither maps onto a
        criterion, so the topic becomes a stated goal awaiting framing. The
        learner keeps their list and the first session re-derives criteria.
        """
        if not isinstance(values, list):
            return cls()
        goals: list[LearningGoal] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            statement = " ".join(str(value.get("name", "")).split())[:200]
            if not statement:
                continue
            goals.append(
                LearningGoal(
                    goal_id=goal_id_for(statement, profile.learning_language),
                    statement=statement,
                    profile=profile,
                    last_worked_at=_optional_float(value.get("last_reviewed")),
                )
            )
        return cls(goals)

    def to_document(self) -> list[dict]:
        return [_goal_to_dict(goal) for goal in self._goals]

    def all(self) -> tuple[LearningGoal, ...]:
        return tuple(self._goals)

    def for_language(self, language: str) -> tuple[LearningGoal, ...]:
        key = _language_base(language)
        return tuple(
            goal
            for goal in self._goals
            if _language_base(goal.profile.learning_language) == key
        )

    def find(self, goal_id: str) -> LearningGoal | None:
        return next((goal for goal in self._goals if goal.goal_id == goal_id), None)

    def find_by_statement(self, statement: str) -> LearningGoal | None:
        key = _normalize(statement)
        return next(
            (goal for goal in self._goals if _normalize(goal.statement) == key), None
        )

    def put(self, goal: LearningGoal) -> None:
        current = self.find(goal.goal_id)
        if current is None:
            self._goals.append(goal)
        else:
            self._goals[self._goals.index(current)] = goal

    def remove(self, goal_id: str) -> bool:
        goal = self.find(goal_id)
        if goal is None:
            return False
        self._goals.remove(goal)
        return True

    def __len__(self) -> int:
        return len(self._goals)


def material_to_dict(material) -> dict:
    """Serialize step material for the client, mirroring the domain shape."""
    return {
        "title": material.title,
        "intro": material.intro,
        "sections": [
            {
                "icon": section.icon,
                "header": section.header,
                "items": list(section.items),
                "text": section.text,
                "highlight": section.highlight,
            }
            for section in material.sections
        ],
    }


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


def _optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _goal_from_dict(data: dict, fallback: LearnerProfile) -> LearningGoal:
    statement = " ".join(str(data.get("statement", "")).split())[:200]
    profile = _profile_from_dict(data, fallback)
    criteria = _criteria_from_list(data.get("criteria"))
    known = {item.criterion_id for item in criteria}
    return LearningGoal(
        goal_id=str(data.get("goal_id") or goal_id_for(statement, profile.learning_language)),
        statement=statement,
        profile=profile,
        material=GoalMaterial(
            text=str(data.get("material_text") or ""),
            source_url=str(data.get("material_url") or ""),
        ),
        criteria=criteria,
        evidence=_evidence_from_list(data.get("evidence"), known),
        next_plan=_plan_from_dict(data.get("next_plan"), known),
        terms=tuple(
            DiscoveredTerm(
                term=str(value.get("term", "")),
                translation=str(value.get("translation", "")),
                context=str(value.get("context", "") or ""),
            )
            for value in data.get("terms", [])
            if isinstance(value, dict) and str(value.get("term", "")).strip()
        ),
        patterns=tuple(
            DiscoveredPattern(
                category=str(value.get("category", "")),
                label=str(value.get("label", "")),
                explanation=str(value.get("explanation", "")),
                example=str(value.get("example", "")),
            )
            for value in data.get("patterns", [])
            if isinstance(value, dict) and str(value.get("label", "")).strip()
        ),
        spent_seconds=max(0.0, float(data.get("spent_seconds", 0.0) or 0.0)),
        created_at=float(data.get("created_at", 0.0) or 0.0),
        last_worked_at=_optional_float(data.get("last_worked_at")),
        achieved_at=_optional_float(data.get("achieved_at")),
    )


def _profile_from_dict(data: dict, fallback: LearnerProfile) -> LearnerProfile:
    try:
        minutes = int(data.get("minutes", fallback.minutes) or fallback.minutes)
    except (TypeError, ValueError):
        minutes = fallback.minutes
    return LearnerProfile(
        proficiency=str(data.get("proficiency") or fallback.proficiency),
        native_language=str(data.get("native_language") or fallback.native_language),
        learning_language=str(
            data.get("learning_language") or fallback.learning_language
        ),
        minutes=max(1, minutes),
    )


def _criteria_from_list(values: object) -> tuple[SuccessCriterion, ...]:
    if not isinstance(values, list):
        return ()
    accepted: list[SuccessCriterion] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        criterion_id = str(value.get("criterion_id", "")).strip()
        statement = " ".join(str(value.get("statement", "")).split())
        try:
            depth = int(value.get("depth", 0))
        except (TypeError, ValueError):
            continue
        if not criterion_id or not statement or not MIN_DEPTH <= depth <= MAX_DEPTH:
            continue
        accepted.append(SuccessCriterion(criterion_id, statement, depth))
    return tuple(accepted)


def _evidence_from_list(values: object, known: set[str]) -> tuple[Evidence, ...]:
    if not isinstance(values, list):
        return ()
    accepted: list[Evidence] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        criterion_id = str(value.get("criterion_id", ""))
        activity = str(value.get("activity", ""))
        outcome = str(value.get("outcome", ""))
        cause = str(value.get("cause", ""))
        # Evidence about a criterion the goal no longer has would skew every
        # status it touches, so it is dropped rather than re-homed.
        if (
            criterion_id not in known
            or activity not in ACTIVITY_DEMAND
            or outcome not in _OUTCOMES
            or cause not in CAUSES
        ):
            continue
        accepted.append(
            Evidence(
                criterion_id=criterion_id,
                activity=activity,  # type: ignore[arg-type]
                outcome=outcome,  # type: ignore[arg-type]
                cause=cause,  # type: ignore[arg-type]
                question=str(value.get("question", "")),
                answer=str(value.get("answer", "") or ""),
                observed_at=float(value.get("observed_at", 0.0) or 0.0),
            )
        )
    return tuple(accepted)


def _plan_from_dict(value: object, known: set[str]) -> RoutePlan | None:
    if not isinstance(value, dict):
        return None
    criterion_id = str(value.get("criterion_id", ""))
    activity = str(value.get("activity", ""))
    reason = str(value.get("reason", ""))
    if criterion_id not in known or activity not in ACTIVITY_DEMAND or reason not in _REASONS:
        return None
    return RoutePlan(criterion_id, activity, reason)  # type: ignore[arg-type]


def _goal_to_dict(goal: LearningGoal) -> dict:
    return {
        "goal_id": goal.goal_id,
        "statement": goal.statement,
        "proficiency": goal.profile.proficiency,
        "native_language": goal.profile.native_language,
        "learning_language": goal.profile.learning_language,
        "minutes": goal.profile.minutes,
        "material_text": goal.material.text,
        "material_url": goal.material.source_url,
        "criteria": [
            {
                "criterion_id": item.criterion_id,
                "statement": item.statement,
                "depth": item.depth,
            }
            for item in goal.criteria
        ],
        "evidence": [
            {
                "criterion_id": item.criterion_id,
                "activity": item.activity,
                "outcome": item.outcome,
                "cause": item.cause,
                "question": item.question,
                "answer": item.answer,
                "observed_at": item.observed_at,
            }
            for item in goal.evidence
        ],
        "next_plan": (
            {
                "criterion_id": goal.next_plan.criterion_id,
                "activity": goal.next_plan.activity,
                "reason": goal.next_plan.reason,
            }
            if goal.next_plan is not None
            else None
        ),
        "terms": [
            {
                "term": item.term,
                "translation": item.translation,
                "context": item.context,
            }
            for item in goal.terms
        ],
        "patterns": [
            {
                "category": item.category,
                "label": item.label,
                "explanation": item.explanation,
                "example": item.example,
            }
            for item in goal.patterns
        ],
        "spent_seconds": goal.spent_seconds,
        "created_at": goal.created_at,
        "last_worked_at": goal.last_worked_at,
        "achieved_at": goal.achieved_at,
    }
