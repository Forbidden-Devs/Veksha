from __future__ import annotations

from dataclasses import dataclass

import pytest

from api import immersion_v2
from learning_core_v2.immersion import ImmersionBlock, ImmersionSentence


def test_immersion_v2_preserves_public_path():
    paths = {route.path for route in immersion_v2.router.routes}

    assert paths == {"/api/immersion/analyze"}


@dataclass
class FakeSettings:
    english_level: str = "intermediate"
    native_lang: str = "en"
    target_lang: str = "ru"


@dataclass
class FakeStorage:
    settings: FakeSettings


class RecordingAnalyzer:
    def __init__(self):
        self.blocks = None
        self.context = None

    async def execute(self, blocks, context):
        self.blocks = blocks
        self.context = context
        return (
            ImmersionBlock(
                (ImmersionSentence("A sentence.", "B1", "Предложение."),)
            ),
        )


@pytest.mark.asyncio
async def test_endpoint_uses_profile_and_preserves_response_shape(monkeypatch):
    analyzer = RecordingAnalyzer()
    monkeypatch.setattr(
        immersion_v2, "get_storage", lambda _username: FakeStorage(FakeSettings())
    )
    monkeypatch.setattr(
        immersion_v2, "build_immersion_analyzer", lambda: analyzer
    )

    response = await immersion_v2.api_immersion_analyze(
        immersion_v2.ImmersionRequest(blocks=["A sentence."]), "tester"
    )

    assert analyzer.context.native_language == "en"
    assert analyzer.context.learning_language == "ru"
    assert analyzer.context.learner_cefr == "B1"
    assert response.blocks[0].sentences[0].translation == "Предложение."
