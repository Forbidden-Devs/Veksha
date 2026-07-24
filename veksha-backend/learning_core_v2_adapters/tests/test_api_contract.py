from dataclasses import dataclass

import pytest

from api import translate_v2
from learning_core_v2.translation import TranslationResult


def test_translation_v2_preserves_public_paths():
    paths = {route.path for route in translate_v2.router.routes}

    assert paths == {"/api/translate", "/api/quick_translate", "/api/explain"}


@dataclass
class FakeSettings:
    english_level: str = "b1"
    native_lang: str = "ru"
    target_lang: str = "en"


@dataclass
class FakeStorage:
    settings: FakeSettings


class RecordingService:
    def __init__(self):
        self.request = None

    async def execute(self, request):
        self.request = request
        return TranslationResult("hello", "ru", True, "привет", "")


@pytest.mark.asyncio
async def test_bidirectional_route_uses_the_users_language_pair(monkeypatch):
    storage = FakeStorage(FakeSettings())
    service = RecordingService()
    monkeypatch.setattr(translate_v2, "get_storage", lambda _username: storage)
    monkeypatch.setattr(translate_v2, "build_translate_text", lambda _storage: service)

    response = await translate_v2._translate(
        translate_v2.TranslateRequest(
            text="привет", source_lang="auto", target_lang="ru", bidirectional=True
        ),
        "tester",
    )

    assert service.request.source_language == "ru"
    assert service.request.target_language == "en"
    assert response.translation == "hello"
