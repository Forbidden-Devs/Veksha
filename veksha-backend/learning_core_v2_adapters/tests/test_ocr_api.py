from types import SimpleNamespace

import pytest

from api import ocr
from learning_core_v2_adapters.openai_responses import LanguageProviderError


def request() -> ocr.RegionTranslationRequest:
    return ocr.RegionTranslationRequest(
        image_data_url="data:image/png;base64,iVBORw0KGgo=",
        source_lang="en",
        target_lang="ru",
    )


def test_ocr_route_is_explicit_and_authenticated():
    assert {route.path for route in ocr.router.routes} == {"/api/ocr/translate-region"}


@pytest.mark.asyncio
async def test_google_text_uses_the_translation_core(monkeypatch):
    async def google(_encoded):
        return "A photographed sentence"

    async def translate(req, _storage, _service):
        assert req.text == "A photographed sentence"
        return SimpleNamespace(
            translation="Сфотографированное предложение",
            detected_source_lang="en",
        )

    monkeypatch.setattr(ocr, "_google_ocr", google)
    monkeypatch.setattr(ocr, "_execute_translation", translate)
    monkeypatch.setattr(ocr, "get_storage", lambda _username: object())
    monkeypatch.setattr(
        ocr,
        "build_deferred_translate_text",
        lambda _storage: (object(), object(), object()),
    )

    response = await ocr.translate_region(request(), "tester")

    assert response.provider == "google"
    assert response.recognized_text == "A photographed sentence"


@pytest.mark.asyncio
async def test_vision_is_used_when_primary_ocr_is_unavailable(monkeypatch):
    async def unavailable(_encoded):
        raise LanguageProviderError("not configured")

    async def vision(_image, _source, _target):
        return {
            "recognized_text": "Fallback text",
            "translation": "Резервный текст",
            "detected_source_lang": "en",
        }

    monkeypatch.setattr(ocr, "_google_ocr", unavailable)
    monkeypatch.setattr(ocr, "_openai_vision", vision)

    response = await ocr.translate_region(request(), "tester")

    assert response.provider == "openai"
    assert response.translation == "Резервный текст"
