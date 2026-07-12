"""
Dual-subtitle translation tests: LLM-output validation and the endpoint with
a stubbed translator (no network).

Run either way:
    python tests/test_subtitles.py
    pytest tests/
"""
import asyncio
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.subtitles import _validate  # noqa: E402
import api.subtitles as api_subtitles  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def test_validate_normalizes_good_output():
    out = _validate({
        "translation_tokens": ["Я", "никогда", "этого", "не", "говорил"],
        "alignment": [[[0], [0]], [[1], [1]], [[2, 3], [2, 3, 4]]],
        "source_lang": "en",
    }, n_src=4)
    assert out["translation_tokens"] == ["Я", "никогда", "этого", "не", "говорил"]
    assert out["alignment"] == [
        {"src": [0], "dst": [0]},
        {"src": [1], "dst": [1]},
        {"src": [2, 3], "dst": [2, 3, 4]},
    ]
    assert out["detected_source_lang"] == "en"


def test_validate_drops_bad_indices_and_duplicates():
    out = _validate({
        "translation_tokens": ["a", "b"],
        "alignment": [
            [[0], [0]],
            [[0], [1]],        # reuses source index 0 -> dropped
            [[7], [1]],        # out of range -> dropped
            [[1], [99]],       # dst out of range -> dropped
            "junk",            # malformed -> dropped
        ],
    }, n_src=2)
    assert out["alignment"] == [{"src": [0], "dst": [0]}]
    assert out["detected_source_lang"] is None


def test_validate_rejects_empty_translation():
    assert _validate({"translation_tokens": [], "alignment": []}, n_src=3) is None
    assert _validate({"alignment": []}, n_src=3) is None


def test_endpoint_with_stubbed_translator():
    orig = api_subtitles.translate_subtitle_line

    async def fake(tokens, source_lang, target_lang):
        assert tokens == ["I", "never", "said", "that"]
        assert target_lang == "ru"
        return {
            "translation_tokens": ["Я", "этого", "не", "говорил"],
            "alignment": [{"src": [0], "dst": [0]}],
            "detected_source_lang": "en",
        }

    api_subtitles.translate_subtitle_line = fake
    try:
        req = api_subtitles.SubtitleTranslateRequest(
            tokens=["I", "never", "said", "that"], source_lang="auto", target_lang="ru")
        resp = asyncio.run(api_subtitles.api_subtitles_translate(req, "tester"))
        assert resp.translation_tokens[0] == "Я"
        assert resp.alignment[0].src == [0]
        assert resp.detected_source_lang == "en"
    finally:
        api_subtitles.translate_subtitle_line = orig


def test_endpoint_maps_llm_failure_to_502():
    orig = api_subtitles.translate_subtitle_line

    async def broken(tokens, source_lang, target_lang):
        raise ValueError("boom")

    api_subtitles.translate_subtitle_line = broken
    try:
        req = api_subtitles.SubtitleTranslateRequest(tokens=["hi"], target_lang="ru")
        try:
            asyncio.run(api_subtitles.api_subtitles_translate(req, "tester"))
            assert False, "expected 502"
        except HTTPException as e:
            assert e.status_code == 502
    finally:
        api_subtitles.translate_subtitle_line = orig


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError:
            failed += 1
            import traceback
            print(f"FAIL {name}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
