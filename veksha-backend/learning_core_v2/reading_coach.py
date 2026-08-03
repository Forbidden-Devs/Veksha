"""Domain policy for deciding whether a page is ready to read."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence


CEFR_BANDS = ("A1", "A2", "B1", "B2", "C1", "C2")
KnowledgeState = Literal["known", "learning", "suggested", "ignored", "unseen"]
ReadingVerdict = Literal["ideal", "too_easy", "too_hard", "close"]


@dataclass(frozen=True, slots=True)
class ReadingToken:
    term: str
    occurrences: int
    cefr: str
    knowledge: KnowledgeState = "unseen"


@dataclass(frozen=True, slots=True)
class ReadingObstacle:
    term: str
    occurrences: int
    cefr: str
    knowledge: KnowledgeState
    reason: Literal["learning", "already_suggested", "above_level", "frequent"]


@dataclass(frozen=True, slots=True)
class ReadingAssessment:
    known_ratio: float
    projected_known_ratio: float
    page_cefr: str
    learner_cefr: str
    verdict: ReadingVerdict
    confidence: Literal["low", "high"]
    unique_terms: int
    obstacles: tuple[ReadingObstacle, ...]


class AssessReading:
    def __init__(self, maximum_obstacles: int = 8) -> None:
        if not 1 <= maximum_obstacles <= 20:
            raise ValueError("maximum obstacles must be between one and twenty")
        self._maximum_obstacles = maximum_obstacles

    def execute(
        self,
        tokens: Sequence[ReadingToken],
        *,
        learner_cefr: str,
    ) -> ReadingAssessment:
        learner = _cefr(learner_cefr)
        normalized = _normalize_tokens(tokens)
        total = sum(token.occurrences for token in normalized)
        if total == 0:
            return ReadingAssessment(0.0, 0.0, "A1", learner, "close", "low", 0, ())

        learner_index = CEFR_BANDS.index(learner)
        known_occurrences = sum(
            token.occurrences
            for token in normalized
            if _is_known(token, learner_index)
        )
        candidates = [
            token
            for token in normalized
            if not _is_known(token, learner_index) and token.knowledge != "ignored"
        ]
        candidates.sort(
            key=lambda token: (
                -_priority(token, learner_index),
                -token.occurrences,
                token.term.casefold(),
            )
        )
        selected = candidates[: self._maximum_obstacles]
        obstacles = tuple(_obstacle(token, learner_index) for token in selected)
        projected = known_occurrences + sum(token.occurrences for token in selected)
        known_ratio = known_occurrences / total
        page_cefr = _page_cefr(normalized, total)
        return ReadingAssessment(
            known_ratio=known_ratio,
            projected_known_ratio=min(1.0, projected / total),
            page_cefr=page_cefr,
            learner_cefr=learner,
            verdict=_verdict(page_cefr, learner, known_ratio),
            confidence="high" if len(normalized) >= 50 else "low",
            unique_terms=len(normalized),
            obstacles=obstacles,
        )


def _normalize_tokens(tokens: Sequence[ReadingToken]) -> tuple[ReadingToken, ...]:
    merged: dict[str, ReadingToken] = {}
    precedence = {"known": 4, "learning": 3, "suggested": 2, "ignored": 1, "unseen": 0}
    for raw in tokens:
        term = " ".join(raw.term.split())
        if not term or raw.occurrences < 1:
            continue
        key = term.casefold()
        current = merged.get(key)
        knowledge = raw.knowledge
        if current is not None and precedence[current.knowledge] > precedence[knowledge]:
            knowledge = current.knowledge
        merged[key] = ReadingToken(
            term=current.term if current else term,
            occurrences=(current.occurrences if current else 0) + raw.occurrences,
            cefr=_cefr(raw.cefr),
            knowledge=knowledge,
        )
    return tuple(merged.values())


def _is_known(token: ReadingToken, learner_index: int) -> bool:
    if token.knowledge == "known":
        return True
    if token.knowledge in {"learning", "suggested", "ignored"}:
        return False
    return CEFR_BANDS.index(token.cefr) <= learner_index


def _priority(token: ReadingToken, learner_index: int) -> int:
    gap = max(0, CEFR_BANDS.index(token.cefr) - learner_index)
    state_bonus = 2 if token.knowledge in {"learning", "suggested"} else 0
    return token.occurrences * (2 + gap) + state_bonus


def _obstacle(token: ReadingToken, learner_index: int) -> ReadingObstacle:
    if token.knowledge == "learning":
        reason = "learning"
    elif token.knowledge == "suggested":
        reason = "already_suggested"
    elif CEFR_BANDS.index(token.cefr) > learner_index:
        reason = "above_level"
    else:
        reason = "frequent"
    return ReadingObstacle(
        token.term,
        token.occurrences,
        token.cefr,
        token.knowledge,
        reason,
    )


def _page_cefr(tokens: Sequence[ReadingToken], total: int) -> str:
    by_band = {band: 0 for band in CEFR_BANDS}
    for token in tokens:
        by_band[token.cefr] += token.occurrences
    covered = 0
    for band in CEFR_BANDS:
        covered += by_band[band]
        if covered / total >= 0.95:
            return band
    return "C2"


def _verdict(page: str, learner: str, known_ratio: float) -> ReadingVerdict:
    gap = CEFR_BANDS.index(page) - CEFR_BANDS.index(learner)
    if known_ratio >= 0.98:
        return "too_easy"
    if gap >= 2 or known_ratio < 0.85:
        return "too_hard"
    if gap == 1 and known_ratio >= 0.90:
        return "ideal"
    return "close"


def _cefr(value: str) -> str:
    normalized = value.strip().upper()
    return normalized if normalized in CEFR_BANDS else "B1"
