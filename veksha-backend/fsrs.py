"""
fsrs.py — FSRS-4.5 spaced-repetition scheduler (pure functions, no I/O).

Replaces the fixed Anki-style interval table: each word carries a memory
state (stability S = interval in days at 90% recall, difficulty D in 1..10),
updated from review outcomes. The default weights are the published FSRS-4.5
parameters; the review_log table (db.py) stores everything needed to fit
per-user weights later.

Ratings follow the FSRS convention:
  1 = Again, 2 = Hard, 3 = Good, 4 = Easy.
The Adaptive Practice Planner grades every review on all four (see
learning_core_v2.practice.suggest_rating) and passes the name through
rating_from_name(); outcome_to_rating() remains for surfaces that only
produce a verdict, such as the Anki-style review endpoint.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# Published FSRS-4.5 default parameters.
WEIGHTS: tuple[float, ...] = (
    0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031,
    1.6474, 0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755,
)

DECAY = -0.5
FACTOR = 19.0 / 81.0  # chosen so that interval(S, r=0.9) == S

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4

_MIN_STABILITY = 0.01
_MAX_STABILITY = 36500.0


@dataclass(frozen=True)
class MemoryState:
    stability: float
    difficulty: float


RATING_NAMES: dict[str, int] = {
    "again": AGAIN,
    "hard": HARD,
    "good": GOOD,
    "easy": EASY,
}


def outcome_to_rating(outcome: str) -> Optional[int]:
    """Map an LLM answer-check outcome to an FSRS rating (None = not a review)."""
    return {"correct": GOOD, "vague": HARD, "incorrect": AGAIN}.get(outcome)


def rating_from_name(name: str) -> Optional[int]:
    """Map a graded rating name to an FSRS rating (None = unknown name)."""
    return RATING_NAMES.get(name.strip().lower())


def rating_name(rating: int) -> str:
    """Inverse of rating_from_name, for logs and stored review rows."""
    for name, value in RATING_NAMES.items():
        if value == rating:
            return name
    return ""


def retrievability(elapsed_days: float, stability: float) -> float:
    """Predicted recall probability after elapsed_days."""
    if stability <= 0:
        return 0.0
    return (1.0 + FACTOR * max(0.0, elapsed_days) / stability) ** DECAY


def interval_days(stability: float, desired_retention: float) -> float:
    """Days until predicted recall drops to desired_retention."""
    return (stability / FACTOR) * (desired_retention ** (1.0 / DECAY) - 1.0)


def _clamp_stability(s: float) -> float:
    return min(max(s, _MIN_STABILITY), _MAX_STABILITY)


def _clamp_difficulty(d: float) -> float:
    return min(max(d, 1.0), 10.0)


def _init_difficulty(rating: int) -> float:
    return _clamp_difficulty(WEIGHTS[4] - (rating - 3) * WEIGHTS[5])


def init_state(rating: int) -> MemoryState:
    """First review of a word (it had no FSRS state yet)."""
    return MemoryState(
        stability=_clamp_stability(WEIGHTS[rating - 1]),
        difficulty=_init_difficulty(rating),
    )


def review(state: MemoryState, rating: int, elapsed_days: float) -> MemoryState:
    """Subsequent review: new memory state from the current one."""
    r = retrievability(elapsed_days, state.stability)
    s, d = state.stability, state.difficulty

    if rating == AGAIN:
        new_s = (
            WEIGHTS[11]
            * d ** (-WEIGHTS[12])
            * ((s + 1.0) ** WEIGHTS[13] - 1.0)
            * math.exp((1.0 - r) * WEIGHTS[14])
        )
        new_s = min(new_s, s)  # forgetting never increases stability
    else:
        hard_penalty = WEIGHTS[15] if rating == HARD else 1.0
        easy_bonus = WEIGHTS[16] if rating == EASY else 1.0
        new_s = s * (
            1.0
            + math.exp(WEIGHTS[8])
            * (11.0 - d)
            * s ** (-WEIGHTS[9])
            * (math.exp((1.0 - r) * WEIGHTS[10]) - 1.0)
            * hard_penalty
            * easy_bonus
        )

    new_d = d - WEIGHTS[6] * (rating - 3)
    new_d = WEIGHTS[7] * _init_difficulty(EASY) + (1.0 - WEIGHTS[7]) * new_d  # mean reversion

    return MemoryState(
        stability=_clamp_stability(new_s),
        difficulty=_clamp_difficulty(new_d),
    )
