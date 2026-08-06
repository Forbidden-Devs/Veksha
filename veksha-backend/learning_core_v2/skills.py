"""Per-skill mastery model for a single lexical sense.

FSRS schedules *when* a sense comes back; this module tracks *which part of
knowing it* is still weak. Every sense carries four independent skills, so a
learner who recognizes ``come across`` while reading but cannot produce it
from a prompt keeps a high recognition confidence and a low recall one.

Confidence is a bounded exponential moving average over the four FSRS
ratings. Senses that predate the skill model simply start neutral: an empty
profile answers with :data:`NEUTRAL_CONFIDENCE` for every skill, which places
them mid-pack instead of flooding the planner as if they were failures.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal


Skill = Literal["recognition", "recall", "contextual_meaning", "listening"]
Rating = Literal["again", "hard", "good", "easy"]

SKILLS: tuple[Skill, ...] = (
    "recognition",
    "recall",
    "contextual_meaning",
    "listening",
)
RATINGS: tuple[Rating, ...] = ("again", "hard", "good", "easy")

NEUTRAL_CONFIDENCE = 0.5

# How much of a single answer is absorbed into the running confidence. High
# enough that two answers visibly move a skill, low enough that one unlucky
# task does not relabel a well-practiced one as weak.
_LEARNING_RATE = 0.4

_RATING_SCORE: dict[Rating, float] = {
    "again": 0.0,
    "hard": 0.45,
    "good": 0.85,
    "easy": 1.0,
}

# An untouched skill is worth probing even when nothing suggests it is weak.
_EXPLORATION_BONUS = 0.12

# A skill left alone for this long drifts back toward the planner's attention.
_STALENESS_HORIZON_SECONDS = 14 * 86400
_STALENESS_WEIGHT = 0.1


@dataclass(frozen=True, slots=True)
class SkillState:
    """Confidence in one skill for one sense."""

    attempts: int = 0
    errors: int = 0
    streak: int = 0
    last_practiced_at: float = 0.0
    confidence: float = NEUTRAL_CONFIDENCE

    @property
    def practiced(self) -> bool:
        return self.attempts > 0

    @property
    def failing(self) -> bool:
        """True while the last answer for this skill was wrong."""
        return self.attempts > 0 and self.streak == 0


@dataclass(frozen=True, slots=True)
class SkillProfile:
    """Immutable set of skill states, stored as pairs so the item stays hashable."""

    entries: tuple[tuple[Skill, SkillState], ...] = ()

    def state(self, skill: Skill) -> SkillState:
        for name, state in self.entries:
            if name == skill:
                return state
        return SkillState()

    def with_state(self, skill: Skill, state: SkillState) -> "SkillProfile":
        if skill not in SKILLS:
            raise ValueError("unknown practice skill")
        retained = tuple(
            (name, value) for name, value in self.entries if name != skill
        )
        return SkillProfile(entries=(*retained, (skill, state)))

    def record(self, skill: Skill, rating: Rating, *, now: float) -> "SkillProfile":
        return self.with_state(skill, record_attempt(self.state(skill), rating, now=now))

    def as_mapping(self) -> dict[Skill, SkillState]:
        return {skill: self.state(skill) for skill in SKILLS}


def record_attempt(state: SkillState, rating: Rating, *, now: float) -> SkillState:
    """Fold one graded answer into a skill state."""
    if rating not in _RATING_SCORE:
        raise ValueError("unknown practice rating")
    target = _RATING_SCORE[rating]
    confidence = state.confidence + _LEARNING_RATE * (target - state.confidence)
    failed = rating == "again"
    return replace(
        state,
        attempts=state.attempts + 1,
        errors=state.errors + (1 if failed else 0),
        streak=0 if failed else state.streak + 1,
        last_practiced_at=max(0.0, now),
        confidence=min(1.0, max(0.0, confidence)),
    )


def weakness(state: SkillState, *, now: float) -> float:
    """How much this skill deserves the next task, in 0..1."""
    score = 1.0 - state.confidence
    if not state.practiced:
        score += _EXPLORATION_BONUS
    elif state.last_practiced_at > 0:
        idle = max(0.0, now - state.last_practiced_at)
        score += _STALENESS_WEIGHT * min(1.0, idle / _STALENESS_HORIZON_SECONDS)
    return min(1.0, max(0.0, score))


def limiting_skill(profile: SkillProfile, *, candidates: tuple[Skill, ...] = SKILLS) -> Skill:
    """The skill holding this sense back — the least confident practiced one.

    Unpracticed skills lose ties: an unanswered skill is unknown, not weak, and
    reporting it as the limit would tell the learner nothing about their gap.
    """
    if not candidates:
        raise ValueError("limiting skill needs at least one candidate")
    return min(
        candidates,
        key=lambda skill: (
            profile.state(skill).confidence,
            not profile.state(skill).practiced,
            SKILLS.index(skill),
        ),
    )
