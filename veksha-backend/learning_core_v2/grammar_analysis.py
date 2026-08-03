"""Grounded grammar analysis for page text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .grammar_memory import GRAMMAR_CATEGORIES


GrammarRole = Literal["subject", "verb", "object", "place", "time", "modifier"]
GRAMMAR_ROLES = frozenset({"subject", "verb", "object", "place", "time", "modifier"})


@dataclass(frozen=True, slots=True)
class GrammarAnalysisRequest:
    text: str
    native_language: str
    learner_level: str


@dataclass(frozen=True, slots=True)
class GrammarSegmentDraft:
    text: str
    role: str
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class GrammarAnnotationDraft:
    text: str
    category: str
    label: str
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class GrammarAnalysisDraft:
    segments: tuple[GrammarSegmentDraft, ...] = ()
    annotations: tuple[GrammarAnnotationDraft, ...] = ()


@dataclass(frozen=True, slots=True)
class GrammarSegment:
    text: str
    role: GrammarRole
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class GrammarAnnotation:
    text: str
    category: str
    label: str
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class GrammarAnalysis:
    segments: tuple[GrammarSegment, ...] = ()
    annotations: tuple[GrammarAnnotation, ...] = ()


class GrammarAnalysisProvider(Protocol):
    async def analyze_grammar(
        self, request: GrammarAnalysisRequest
    ) -> GrammarAnalysisDraft: ...


class AnalyzeGrammar:
    def __init__(self, provider: GrammarAnalysisProvider) -> None:
        self._provider = provider

    async def execute(self, request: GrammarAnalysisRequest) -> GrammarAnalysis:
        text = request.text or ""
        if not text.strip():
            return GrammarAnalysis()
        if len(text) > 6000:
            raise ValueError("grammar analysis text is too long")
        native_language = request.native_language.strip().lower().replace("_", "-")
        if not native_language:
            raise ValueError("grammar analysis requires a native language")
        normalized = GrammarAnalysisRequest(
            text=text,
            native_language=native_language,
            learner_level=request.learner_level.strip() or "unknown",
        )
        draft = await self._provider.analyze_grammar(normalized)
        return GrammarAnalysis(
            segments=_ground_segments(text, draft.segments),
            annotations=_ground_annotations(text, draft.annotations),
        )


def _ground_segments(
    text: str,
    drafts: tuple[GrammarSegmentDraft, ...],
) -> tuple[GrammarSegment, ...]:
    result: list[GrammarSegment] = []
    cursor = 0
    for draft in drafts:
        segment = draft.text
        role = draft.role.strip().lower()
        if not segment.strip() or role not in GRAMMAR_ROLES:
            continue
        index = text.find(segment, cursor)
        if index < 0:
            continue
        result.append(
            GrammarSegment(
                text=segment,
                role=role,
                explanation=draft.explanation.strip()[:160],
            )
        )
        cursor = index + len(segment)
    return tuple(result)


def _ground_annotations(
    text: str,
    drafts: tuple[GrammarAnnotationDraft, ...],
) -> tuple[GrammarAnnotation, ...]:
    result: list[tuple[int, GrammarAnnotation]] = []
    seen: set[tuple[str, str, str]] = set()
    for draft in drafts:
        segment = draft.text
        category = draft.category.strip().lower()
        label = draft.label.strip()[:80]
        if not segment.strip() or category not in GRAMMAR_CATEGORIES or not label:
            continue
        index = text.find(segment)
        signature = (segment, category, label.casefold())
        if index < 0 or signature in seen:
            continue
        seen.add(signature)
        result.append(
            (
                index,
                GrammarAnnotation(
                    text=segment,
                    category=category,
                    label=label,
                    explanation=draft.explanation.strip()[:240],
                ),
            )
        )
    result.sort(key=lambda item: (item[0], len(item[1].text)))
    return tuple(item for _, item in result[:6])
