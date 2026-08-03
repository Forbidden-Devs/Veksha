from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from learning_core_v2.explanation import ExplainText, ExplanationRequest


@dataclass
class StubExplanationProvider:
    response: str
    requests: list[ExplanationRequest] = field(default_factory=list)

    async def explain(self, request: ExplanationRequest) -> str:
        self.requests.append(request)
        return self.response


@pytest.mark.asyncio
async def test_explanation_normalizes_request_and_result():
    provider = StubExplanationProvider("  Used for movement.  ")

    result = await ExplainText(provider).execute(
        ExplanationRequest("  run ", " бежать ", " b1 ", " ru ", " en ")
    )

    assert result.explanation == "Used for movement."
    assert provider.requests == [
        ExplanationRequest("run", "бежать", "b1", "ru", "en")
    ]


@pytest.mark.asyncio
async def test_explanation_rejects_blank_text_before_provider_call():
    provider = StubExplanationProvider("unused")

    with pytest.raises(ValueError, match="text must not be empty"):
        await ExplainText(provider).execute(
            ExplanationRequest(" ", "", "b1", "ru", "en")
        )

    assert provider.requests == []
