"""Use case for expanding a translation into a learner-facing explanation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExplanationRequest:
    text: str
    translation: str
    proficiency: str
    native_language: str
    learning_language: str


@dataclass(frozen=True, slots=True)
class ExplanationResult:
    explanation: str


class ExplanationProvider(Protocol):
    async def explain(self, request: ExplanationRequest) -> str:
        """Explain meaning and usage without changing user state."""


class ExplainText:
    def __init__(self, provider: ExplanationProvider) -> None:
        self._provider = provider

    async def execute(self, request: ExplanationRequest) -> ExplanationResult:
        text = request.text.strip()
        if not text:
            raise ValueError("text must not be empty")

        normalized = ExplanationRequest(
            text=text,
            translation=request.translation.strip(),
            proficiency=request.proficiency.strip(),
            native_language=request.native_language.strip() or "en",
            learning_language=request.learning_language.strip() or "en",
        )
        explanation = (await self._provider.explain(normalized)).strip()
        if not explanation:
            raise ValueError("explanation provider returned empty text")
        return ExplanationResult(explanation=explanation)
