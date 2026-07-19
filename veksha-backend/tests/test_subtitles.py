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

import llm.subtitles as llm_subtitles  # noqa: E402
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


def test_batch_translator_uses_one_contextual_call_and_line_cache():
    original_call = llm_subtitles._call
    original_get = llm_subtitles.db_cache.cache_get
    original_set = llm_subtitles.db_cache.cache_set
    cache = {}
    calls = []

    async def fake_get(namespace, key):
        return cache.get((namespace, key))

    async def fake_set(namespace, key, value):
        cache[(namespace, key)] = value

    async def fake_call(**kwargs):
        calls.append(kwargs)
        return """{"lines":[
          {"index":0,"translation_tokens":["Привет"],"alignment":[[[0],[0]]],"source_lang":"en"},
          {"index":1,"translation_tokens":["Дальше"],"alignment":[[[0],[0]]],"source_lang":"en"}
        ]}"""

    llm_subtitles._call = fake_call
    llm_subtitles.db_cache.cache_get = fake_get
    llm_subtitles.db_cache.cache_set = fake_set
    try:
        lines = [["Hello"], ["Next"]]
        first = asyncio.run(llm_subtitles.translate_subtitle_batch(lines, "auto", "ru"))
        second = asyncio.run(llm_subtitles.translate_subtitle_batch(lines, "auto", "ru"))
        assert [item["translation_tokens"][0] for item in first] == ["Привет", "Дальше"]
        assert second == first
        assert len(calls) == 1
        assert calls[0]["call_name"] == "dualsub_batch"
    finally:
        llm_subtitles._call = original_call
        llm_subtitles.db_cache.cache_get = original_get
        llm_subtitles.db_cache.cache_set = original_set


def test_batch_translator_retries_only_omitted_cues():
    original_call = llm_subtitles._call
    original_line = llm_subtitles.translate_subtitle_line
    original_get = llm_subtitles.db_cache.cache_get
    original_set = llm_subtitles.db_cache.cache_set
    retried = []

    async def fake_get(namespace, key):
        return None

    async def fake_set(namespace, key, value):
        return None

    async def partial_call(**kwargs):
        return """{"lines":[
          {"index":0,"translation_tokens":["Первая"],"alignment":[[[0],[0]]],"source_lang":"en"}
        ]}"""

    async def retry_line(tokens, source_lang, target_lang):
        retried.append(tokens)
        return {
            "translation_tokens": ["Вторая"],
            "alignment": [{"src": [0], "dst": [0]}],
            "detected_source_lang": "en",
        }

    llm_subtitles._call = partial_call
    llm_subtitles.translate_subtitle_line = retry_line
    llm_subtitles.db_cache.cache_get = fake_get
    llm_subtitles.db_cache.cache_set = fake_set
    try:
        result = asyncio.run(llm_subtitles.translate_subtitle_batch(
            [["First"], ["Second"]], "auto", "ru",
        ))
        assert [item["translation_tokens"][0] for item in result] == ["Первая", "Вторая"]
        assert retried == [["Second"]]
    finally:
        llm_subtitles._call = original_call
        llm_subtitles.translate_subtitle_line = original_line
        llm_subtitles.db_cache.cache_get = original_get
        llm_subtitles.db_cache.cache_set = original_set


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


def test_batch_endpoint_sanitizes_and_preserves_order():
    orig = api_subtitles.translate_subtitle_batch

    async def fake(lines, source_lang, target_lang):
        assert lines == [["Hello", "there"], ["Next", "line"]]
        assert source_lang == "auto"
        assert target_lang == "ru"
        return [
            {
                "translation_tokens": ["Привет"],
                "alignment": [{"src": [0, 1], "dst": [0]}],
                "detected_source_lang": "en",
            },
            {
                "translation_tokens": ["Дальше"],
                "alignment": [{"src": [0, 1], "dst": [0]}],
                "detected_source_lang": "en",
            },
        ]

    api_subtitles.translate_subtitle_batch = fake
    try:
        req = api_subtitles.SubtitleBatchTranslateRequest(
            lines=[[" Hello ", "there"], ["Next", "line"]], target_lang="ru",
        )
        resp = asyncio.run(api_subtitles.api_subtitles_translate_batch(req, "tester"))
        assert [line.translation_tokens[0] for line in resp.lines] == ["Привет", "Дальше"]
    finally:
        api_subtitles.translate_subtitle_batch = orig


def test_batch_endpoint_rejects_oversized_line():
    req = api_subtitles.SubtitleBatchTranslateRequest(
        lines=[["word"] * (api_subtitles.MAX_TOKENS + 1)], target_lang="ru",
    )
    try:
        asyncio.run(api_subtitles.api_subtitles_translate_batch(req, "tester"))
        assert False, "expected 400"
    except HTTPException as e:
        assert e.status_code == 400


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
